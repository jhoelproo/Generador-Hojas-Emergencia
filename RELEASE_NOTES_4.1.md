# Generador de Hojas de Emergencia 4.1.0

## Cambios principales

- Los identificadores de atencion son permanentes y ya no se renumeran.
- Cada atencion queda vinculada a un paciente, dia operativo y turno trazables.
- Se bloquean duplicados accidentales dentro del mismo dia operativo.
- Los reingresos requieren una justificacion y conservan la referencia original.
- La anulacion es logica y auditada; no destruye el historial clinico.
- La purga total de pacientes de prueba exige autorizacion administrativa, motivo y confirmacion reforzada.
- Se incorporan respaldos verificados, restauracion controlada y comprobacion de integridad SQLite.
- La auditoria registra creaciones, cambios, anulaciones y operaciones administrativas.
- PDF, Excel e impresion tienen estados recuperables y pueden reintentarse sin duplicar atenciones.
- La interfaz mejora su respuesta en pantallas pequenas, la navegacion por teclado y los mensajes de estado.
- La edicion ordinaria de pacientes y atenciones ya no requiere PIN y conserva una auditoria completa del operador.
- La opcion "Impresiones y documentos pendientes" explica y recupera las etapas que fallaron sin duplicar registros.
- Se incorpora actualizacion remota desde GitHub Releases con verificacion SHA-256 y un actualizador externo.

## Actualizacion

1. Cierre cualquier copia anterior de la aplicacion y Microsoft Excel.
2. Conserve el respaldo automatico que se crea antes de migrar la base de datos.
3. Ejecute `GENERADOR DE HOJAS 4.1.exe` con el mismo usuario de Windows que opera el sistema.
4. Verifique el turno vigente, la impresora y una atencion de prueba antes del uso asistencial.

La primera apertura migra los datos existentes sin cambiar los ID historicos. No interrumpa ese proceso.

## Privacidad y entrega

El paquete de instalacion no contiene bases de datos, listados Excel, configuraciones operativas, reportes, documentos generados ni archivos de log. Los datos reales permanecen fuera del ejecutable en la ubicacion protegida de la aplicacion.

Compruebe el archivo `SHA256SUMS.txt` antes de instalar una copia transferida por red o dispositivo externo.
