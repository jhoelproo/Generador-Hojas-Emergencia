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
