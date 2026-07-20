# Generador de Hojas de Emergencia 4.1.9

- La sección Usuarios presenta un panel moderno dividido entre el catálogo y la corrección independiente del turno actual.
- Añadir y editar usuarios se realiza mediante ventanas emergentes; eliminar permanece como acción directa y confirmada.
- Corregir al representante del turno actual no imprime, no cierra el turno y no modifica pacientes, atenciones, numeración ni hora de inicio.
- La corrección actualiza únicamente la GUI, el encabezado del Excel y el nombre usado en los reportes PDF posteriores.
- Se eliminó la recuperación automática que podía crear un turno al iniciar desde un Excel existente.
- Si hay pacientes en Excel pero falta un turno configurado, el listado se conserva intacto y se solicita una confirmación manual.
- Ningún cambio de turno se ejecuta automáticamente durante sábado, domingo o al cruzar un horario.

- El representante del turno se escribe libremente; las coincidencias aparecen debajo como sugerencias y nunca bloquean la escritura.
- Los valores “No disponible”, “No configurado” y otros marcadores equivalentes ya no pueden guardarse como representantes.
- Configuración interna incorpora la sección Usuarios entre Respaldos y Preferencias para añadir, editar, eliminar o seleccionar representantes.
- Corregir el representante del turno actual solo actualiza la GUI, el encabezado del Excel y los reportes futuros; no reinicia el turno ni modifica pacientes o atenciones.
- Los usuarios eliminados del catálogo no reaparecen por existir en turnos históricos.

- Al editar una atención, el nombre y el sexo se guardan en el registro y el PDF archivado se regenera con los datos nuevos.
- El formulario principal inicia y se limpia con sexo Femenino seleccionado por defecto.
- La GUI y el Excel resuelven el mismo identificador de turno y verifican sus conteos para evitar resúmenes en cero.
- Un Excel recuperado del mismo turno conserva su conteo visible y nunca se sobrescribe cuando la base todavía no contiene sus filas.
- Los conflictos de NSS detectados durante una edición se envían a Revisión NSS sin impedir el guardado ni la generación del documento.

- Al actualizar el NSS de una ficha con cedula se elimina el vinculo anterior y solo queda vigente el NSS nuevo.
- Si un NSS sin cedula aparece con nombre y telefono diferentes, la atencion y la hoja continúan sin interrupcion.
- Esos casos aparecen exclusivamente en Configuracion > Revision NSS para conservar, desvincular o fusionar fichas.
- Los respaldos con mas de cuatro dias se eliminan automaticamente, incluidos formatos antiguos sin manifiesto.
- Se retiro el boton duplicado de revision de conflictos junto al acceso de Historial.

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
- Se corrige la recuperacion de permisos de Windows para que un log con ACL danada nunca impida abrir la aplicacion.
- El historial coloca el foco directamente en la busqueda al abrirse.
- Las atenciones pueden anularse sin PIN, conservando confirmacion, motivo obligatorio y auditoria del operador.

## Actualizacion

1. Cierre cualquier copia anterior de la aplicacion y Microsoft Excel.
2. Conserve el respaldo automatico que se crea antes de migrar la base de datos.
3. Ejecute `GENERADOR DE HOJAS 4.1.exe` con el mismo usuario de Windows que opera el sistema.
4. Verifique el turno vigente, la impresora y una atencion de prueba antes del uso asistencial.

La primera apertura migra los datos existentes sin cambiar los ID historicos. No interrumpa ese proceso.

## Privacidad y entrega

El paquete de instalacion no contiene bases de datos, listados Excel, configuraciones operativas, reportes, documentos generados ni archivos de log. Los datos reales permanecen fuera del ejecutable en la ubicacion protegida de la aplicacion.

Compruebe el archivo `SHA256SUMS.txt` antes de instalar una copia transferida por red o dispositivo externo.
