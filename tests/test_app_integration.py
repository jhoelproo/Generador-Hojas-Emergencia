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


def test_daily_duplicate_identity_conflict_reentry_and_output_states(tmp_path, monkeypatch):
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
    with pytest.raises(module.ConflictoIdentidadError):
        manager.guardar_atencion(
            patient_data(Cédula="00212345679"),
            "GENERAL",
            shift,
        )
    conflict_ids = manager.obtener_o_registrar_conflictos_cedula(
        "002-1234567-9",
        "La cedula pertenece a una ficha diferente del NSS indicado.",
    )
    assert len(conflict_ids) == 1
    assert manager.obtener_o_registrar_conflictos_cedula("00212345679") == conflict_ids
    targeted = {
        int(row["id"]): row for row in manager.listar_conflictos_identidad(True, 1000)
    }
    assert targeted[conflict_ids[0]]["atencion_id"] == second_id
    assert targeted[conflict_ids[0]]["tipo"] == "CONFLICTO_CEDULA_DETECTADO"

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
