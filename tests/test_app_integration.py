from __future__ import annotations

import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest


def load_application(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EMERGENCIAS_DATA_DIR", str(tmp_path / "data"))
    source = Path(__file__).parents[1] / "facturacion_tabs (1).py"
    spec = importlib.util.spec_from_file_location("facturacion_integration", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def valid_shift(module):
    return {
        "representante": "OPERADOR DE PRUEBA",
        "turno_codigo": "8AM_8AM",
        "fecha_base": module.fecha_base_operativa_actual(),
        "inicio_real_dt": datetime.now(),
    }


def patient_data(**overrides):
    data = {
        "Nombre": "PACIENTE PRUEBA UNO",
        "Sexo": "Masculino",
        "Edad_num": 31,
        "Unidad": "Años",
        "Cédula": "00112345678",
        "Teléfono": "8095550101",
        "Dirección": "DIRECCION DE PRUEBA",
        "Nacionalidad": "DOMINICANA",
        "Aseguradora (ARS)": "SENASA CONTRIBUTIVO",
        "NSS": "123456789",
        "Fecha": datetime.now().strftime("%d/%m/%Y"),
        "Hora": datetime.now().strftime("%I:%M %p"),
        "TipoAtencion": "EMERGENCIA",
    }
    data.update(overrides)
    return data


def test_daily_duplicate_identity_precedence_reentry_and_output_states(tmp_path, monkeypatch):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    shift = valid_shift(module)

    first_id = manager.guardar_atencion(patient_data(), "GENERAL", shift)
    with pytest.raises(sqlite3.IntegrityError, match="ya tiene una atención"):
        manager.guardar_atencion(patient_data(), "GENERAL", shift)

    second_id = manager.guardar_atencion(
        patient_data(
            Nombre="PACIENTE PRUEBA DOS",
            Cédula="00212345679",
            Teléfono="8095550102",
            NSS="987654321",
        ),
        "GENERAL",
        shift,
    )
    # La cédula tiene prioridad. Aunque el NSS corresponda a la primera ficha,
    # se reconoce que la segunda ya tiene una atención en el día.
    with pytest.raises(sqlite3.IntegrityError, match="ya tiene una atención"):
        manager.guardar_atencion(
            patient_data(Cédula="00212345679"),
            "GENERAL",
            shift,
        )
    with manager._connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM identidad_conflictos WHERE estado='PENDIENTE'"
        ).fetchone()[0] == 0

    reentry_id = manager.guardar_atencion(
        patient_data(
            NSS="",
            Cédula="",
            EsReingreso=True,
            AtencionOrigenId=first_id,
            MotivoReingreso="Regreso clinico autorizado para prueba",
            AutorizadoPor="SUPERVISOR DE PRUEBA",
        ),
        "GENERAL",
        shift,
    )
    original = manager.obtener_atencion_por_id(first_id)
    reentry = manager.obtener_atencion_por_id(reentry_id)
    assert reentry["paciente_id"] == original["paciente_id"]
    assert reentry["atencion_origen_id"] == first_id
    assert second_id != reentry_id

    manager.actualizar_trabajo_salida(first_id, "excel", "COMPLETADO")
    manager.actualizar_trabajo_salida(first_id, "pdf", "COMPLETADO")
    manager.actualizar_trabajo_salida(first_id, "impresion", "ENVIADO", incrementar_intento=True)
    output = manager.obtener_trabajo_salida(first_id)
    assert (output["excel_estado"], output["pdf_estado"], output["impresion_estado"]) == (
        "COMPLETADO",
        "COMPLETADO",
        "ENVIADO",
    )
    assert output["intentos"] == 1

    assert manager.borrar_atencion(
        second_id,
        motivo="Registro duplicado de prueba",
        usuario="OPERADOR DE PRUEBA",
    ) is True
    annulled = manager.obtener_atencion_por_id(second_id)
    assert annulled["estado"] == "ANULADA"
    assert annulled["anulada_por"] == "OPERADOR DE PRUEBA"
    with manager._connect() as connection:
        audit = connection.execute(
            "SELECT accion,actor_rol,usuario FROM atenciones_auditoria "
            "WHERE atencion_id=? ORDER BY id DESC LIMIT 1",
            (second_id,),
        ).fetchone()
    assert audit == ("ANULACION", "OPERADOR", "OPERADOR DE PRUEBA")

    destination_results = manager.buscar_pacientes_avanzado("PACIENTE PRUEBA UNO")
    assert destination_results
    assert destination_results[0]["paciente_id"] == original["paciente_id"]


def test_new_nss_replaces_previous_identifier_for_same_cedula(tmp_path, monkeypatch):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    original_nss = "123456789"
    nuevo_nss = "555666777"
    nss_editado = "888999000"

    patient_id = manager.guardar_paciente(patient_data(NSS=original_nss))
    assert manager.guardar_paciente(patient_data(NSS=nuevo_nss)) == patient_id
    _, updated_patients = manager.actualizar_datos_paciente_por_identidad(
        f"P:{patient_id}", patient_data(NSS=nss_editado), actualizar_ficha=True
    )
    assert updated_patients == 1

    with manager._connect() as connection:
        identifiers = connection.execute(
            "SELECT valor_normalizado FROM paciente_identificadores "
            "WHERE paciente_id=? AND tipo='NSS' AND activo=1",
            (patient_id,),
        ).fetchall()
        patient_nss = connection.execute(
            "SELECT nss_clean FROM pacientes WHERE id=?", (patient_id,)
        ).fetchone()[0]
    assert identifiers == [(nss_editado,)]
    assert patient_nss == nss_editado


def test_nss_without_cedula_keeps_flow_and_creates_admin_review(tmp_path, monkeypatch):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    shift = valid_shift(module)
    shared_nss = "444555666"

    first_id = manager.guardar_atencion(
        patient_data(
            Nombre="PACIENTE SIN CEDULA UNO", Cédula="", NSS=shared_nss,
            Teléfono="8095550201",
        ),
        "GENERAL",
        shift,
    )
    inicio, fin = module.obtener_rango_turno_efectivo(shift)
    contexto = manager.obtener_contexto_turno(shift)
    assert manager.buscar_atencion_en_turno(
        shared_nss,"",inicio,fin,turno_id=contexto["turno_id"],
        dia_operativo_id=contexto["dia_operativo_id"],
        nombre="PACIENTE SIN CEDULA DOS",telefono="8095550202",
    ) is None
    second_id = manager.guardar_atencion(
        patient_data(
            Nombre="PACIENTE SIN CEDULA DOS", Cédula="", NSS=shared_nss,
            Teléfono="8095550202",
        ),
        "GENERAL",
        shift,
    )

    first = manager.obtener_atencion_por_id(first_id)
    second = manager.obtener_atencion_por_id(second_id)
    assert first["paciente_id"] != second["paciente_id"]
    assert second["identidad_estado"] == "NSS_EN_REVISION"
    assert manager.obtener_trabajo_salida(second_id) is not None
    revisions = manager.listar_revisiones_nss(True)
    assert len(revisions) == 1
    assert revisions[0]["atencion_id"] == second_id
    assert revisions[0]["paciente_referencia_id"] == first["paciente_id"]

    manager.resolver_revision_nss(
        revisions[0]["id"],
        "FUSIONAR_CON_EXISTENTE",
        "ADMIN PRUEBA",
        "Mismo paciente confirmado administrativamente",
    )
    merged = manager.obtener_atencion_por_id(second_id)
    assert merged["paciente_id"] == first["paciente_id"]
    assert merged["es_reingreso"] == 1
    assert merged["atencion_origen_id"] == first_id
    assert manager.listar_revisiones_nss(True) == []


def test_edit_attention_updates_sex_and_invalidates_old_pdf(tmp_path, monkeypatch):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    shift = valid_shift(module)
    attention_id = manager.guardar_atencion(patient_data(), "GENERAL", shift)

    old_pdf = tmp_path / "old.pdf"
    old_pdf.write_bytes(b"%PDF-1.4 old snapshot")
    manager.registrar_documento(
        attention_id, "HOJA_EMERGENCIA", str(old_pdf), "GENERAL"
    )
    manager.actualizar_trabajo_salida(
        attention_id,
        "pdf",
        "COMPLETADO",
        pdf_path=str(old_pdf),
        pdf_sha256="old",
    )

    edited = patient_data(
        Nombre="PACIENTE NOMBRE ACTUALIZADO",
        Sexo="Femenino",
    )
    edited.update({"Hoja": "GENERAL"})
    assert manager.actualizar_atencion_especifica(attention_id, edited) == 1

    current = manager.obtener_atencion_por_id(attention_id)
    assert current["nombre"] == "PACIENTE NOMBRE ACTUALIZADO"
    assert current["sexo"] == "Femenino"
    assert manager.obtener_documento_atencion(attention_id) is None
    output = manager.obtener_trabajo_salida(attention_id)
    assert output["pdf_estado"] == "PENDIENTE"
    assert output["pdf_path"] is None
    assert output["pdf_sha256"] is None

    regenerated = module.regenerar_pdf_archivado(manager, attention_id)
    assert regenerated
    text = "\n".join(
        page.extract_text() or "" for page in module.PdfReader(regenerated).pages
    )
    assert "PACIENTE NOMBRE ACTUALIZADO" in text
    assert "Femenino" in text


def test_edit_nss_conflict_is_logged_without_blocking(tmp_path, monkeypatch):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    shift = valid_shift(module)
    first_id = manager.guardar_atencion(
        patient_data(
            Nombre="REFERENCIA NSS",
            Cédula="",
            NSS="111222333",
            Teléfono="8095550301",
        ),
        "GENERAL",
        shift,
    )
    second_id = manager.guardar_atencion(
        patient_data(
            Nombre="PACIENTE EDITABLE",
            Cédula="",
            NSS="777888999",
            Teléfono="8095550302",
        ),
        "GENERAL",
        shift,
    )
    edited = patient_data(
        Nombre="PACIENTE EDITABLE",
        Sexo="Femenino",
        Cédula="",
        NSS="111222333",
        Teléfono="8095550302",
    )
    edited["Hoja"] = "GENERAL"

    assert manager.actualizar_atencion_especifica(second_id, edited) == 1
    current = manager.obtener_atencion_por_id(second_id)
    assert current["identidad_estado"] == "NSS_EN_REVISION"
    assert current["requiere_revision"] == 1
    revisions = manager.listar_revisiones_nss(True)
    revision = next(row for row in revisions if row["atencion_id"] == second_id)
    assert revision["paciente_referencia_id"] == manager.obtener_atencion_por_id(
        first_id
    )["paciente_id"]


def test_gui_summary_and_excel_use_same_turn_after_start_time_changes(tmp_path, monkeypatch):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    shift = valid_shift(module)
    for index in range(85):
        manager.guardar_atencion(
            patient_data(
                Nombre=f"PACIENTE LISTADO {index:03d}",
                Cédula=f"001{index:08d}",
                NSS=f"9{index:08d}",
                Teléfono=f"80955{index:05d}",
            ),
            "GENERAL",
            shift,
        )

    shifted = dict(shift)
    shifted["inicio_real_dt"] = shift["inicio_real_dt"].replace(
        minute=(shift["inicio_real_dt"].minute + 1) % 60
    )
    context = manager.buscar_contexto_turno_existente(shifted)
    assert context is not None

    module.guardar_turno_config(
        shifted["representante"],
        shifted["turno_codigo"],
        shifted["fecha_base"],
        shifted["inicio_real_dt"],
    )
    assert module.reconstruir_excel_turno(manager, shifted) == 85
    summary = manager.resumen_turno_actual()
    assert summary["total"] == 85
    assert module.resumen_excel_actual_simple(shifted)["total"] == 85


def test_gui_uses_matching_recovered_excel_instead_of_showing_zero(
    tmp_path, monkeypatch
):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    shift = valid_shift(module)
    module.guardar_turno_config(
        shift["representante"],
        shift["turno_codigo"],
        shift["fecha_base"],
        shift["inicio_real_dt"],
    )
    module.verificar_o_crear_excel()
    workbook = module.openpyxl.load_workbook(module.EXCEL_PATH)
    sheet = workbook.active
    visual = module.obtener_datos_turno_visual(
        shift["fecha_base"], shift["turno_codigo"]
    )
    sheet["A3"] = (
        f"{shift['representante']} {visual['fecha_label']}"
    )
    sheet["A4"] = visual["turno_label"]
    for index in range(80):
        sheet.append(
            [index + 1, f"PACIENTE RECUPERADO {index:03d}", "GENERAL", "SENASA"]
        )
    workbook.save(module.EXCEL_PATH)
    workbook.close()

    summary = manager.resumen_turno_actual()
    assert summary["total"] == 80
    assert summary["GENERAL"] == 80
    assert summary["_fuente"] == "EXCEL_RECUPERADO"


def test_representative_catalog_rejects_placeholders_and_honors_deletions(
    tmp_path, monkeypatch
):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    shift = valid_shift(module)
    manager.obtener_contexto_turno(shift)

    assert module.es_representante_valido("María Pérez")
    assert not module.es_representante_valido("No disponible")
    assert not module.es_representante_valido("Nombre del representante")
    assert module.guardar_turno_config(
        "No disponible",
        shift["turno_codigo"],
        shift["fecha_base"],
        shift["inicio_real_dt"],
    ) is False

    assert module.guardar_catalogo_representantes(
        ["MARIA PEREZ", "ANA LOPEZ", "NO DISPONIBLE"]
    )
    assert module.cargar_representantes(manager) == ["ANA LOPEZ", "MARIA PEREZ"]

    assert module.guardar_catalogo_representantes(["MARIA PEREZ"])
    # Los nombres históricos de la BD no vuelven a aparecer después de eliminarse
    # del catálogo administrado.
    assert module.cargar_representantes(manager) == ["MARIA PEREZ"]

    assert module.guardar_turno_config(
        "REPRESENTANTE ACTUAL",
        shift["turno_codigo"],
        shift["fecha_base"],
        shift["inicio_real_dt"],
    )
    assert module.cargar_representantes(
        manager, incluir_actual=False
    ) == ["MARIA PEREZ"]
    assert module.cargar_representantes(manager) == [
        "MARIA PEREZ",
        "REPRESENTANTE ACTUAL",
    ]


def test_change_current_representative_only_updates_turn_headers_and_reports(
    tmp_path, monkeypatch
):
    module = load_application(tmp_path, monkeypatch)
    manager = module.DatabaseManager()
    shift = valid_shift(module)
    module.guardar_turno_config(
        shift["representante"],
        shift["turno_codigo"],
        shift["fecha_base"],
        shift["inicio_real_dt"],
    )
    attention_id = manager.guardar_atencion(patient_data(), "GENERAL", shift)
    module.reconstruir_excel_turno(manager, shift)
    before_attention = manager.obtener_atencion_por_id(attention_id)
    before_config = module.cargar_turno_config(permitir_vencido=True)

    updated = module.actualizar_representante_turno_actual(
        manager, "REPRESENTANTE CORREGIDA"
    )

    after_attention = manager.obtener_atencion_por_id(attention_id)
    after_config = module.cargar_turno_config(permitir_vencido=True)
    context = manager.buscar_contexto_turno_existente(after_config)
    with manager._connect() as connection:
        db_representative = connection.execute(
            "SELECT representante FROM turnos WHERE id=?",
            (context["turno_id"],),
        ).fetchone()[0]

    assert updated["representante"] == "REPRESENTANTE CORREGIDA"
    assert after_config["representante"] == "REPRESENTANTE CORREGIDA"
    assert after_config["inicio_real"] == before_config["inicio_real"]
    assert db_representative == "REPRESENTANTE CORREGIDA"
    assert after_attention == before_attention

    workbook = module.openpyxl.load_workbook(
        module.EXCEL_PATH, read_only=True, data_only=True
    )
    sheet = workbook.active
    assert "REPRESENTANTE CORREGIDA" in str(sheet["A3"].value)
    assert str(sheet["B6"].value) == patient_data()["Nombre"]
    workbook.close()

    report_summary = module.construir_resumen_turno(manager, after_config)
    assert report_summary["representante"] == "REPRESENTANTE CORREGIDA"
    assert report_summary["total_general"] == 1


def test_saturday_excel_never_creates_or_changes_shift_automatically(
    tmp_path, monkeypatch
):
    module = load_application(tmp_path, monkeypatch)
    module.DatabaseManager()
    module.verificar_o_crear_excel()
    workbook = module.openpyxl.load_workbook(module.EXCEL_PATH)
    sheet = workbook.active
    sheet["A3"] = "REPRESENTANTE SABADO 18/07/2026 AL 19/07/2026"
    sheet["A4"] = "DESDE 8:00 AM A 8:00 PM"
    sheet.append([1, "PACIENTE CONSERVADO", "GENERAL", "SENASA"])
    workbook.save(module.EXCEL_PATH)
    workbook.close()

    assert not module.os.path.exists(module.TURNOS_CFG)
    assert module.excel_requiere_turno_manual() is True
    assert not module.os.path.exists(module.TURNOS_CFG)
    assert module.cargar_turno_config(permitir_vencido=True) is None

    workbook = module.openpyxl.load_workbook(
        module.EXCEL_PATH, read_only=True, data_only=True
    )
    assert workbook.active["B6"].value == "PACIENTE CONSERVADO"
    workbook.close()
