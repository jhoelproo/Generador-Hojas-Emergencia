# Generador de Hojas de Emergencia

Aplicacion de escritorio para registrar atenciones de emergencia, generar la hoja clinica, actualizar el listado del turno e imprimir dentro del flujo operativo del hospital.

## Version 4.1.9

- Pacientes, atenciones, dias operativos y turnos tienen relaciones trazables.
- Se bloquean duplicados dentro del mismo dia operativo y se permiten reingresos autorizados.
- La cedula valida tiene prioridad y cada NSS nuevo reemplaza el anterior de esa ficha.
- Un NSS repetido sin cedula nunca detiene la hoja; queda en Revision NSS dentro de Configuracion.
- Los respaldos se eliminan automaticamente al superar cuatro dias de antiguedad.
- Los ID historicos son permanentes y las anulaciones son logicas.
- La edicion ordinaria no requiere PIN; cada cambio conserva actor, fecha, equipo y valores antes/despues.
- La purga de pacientes de prueba, restauracion y administracion siguen protegidas por PIN.
- PDF, Excel e impresion usan estados recuperables sin crear atenciones duplicadas al reintentar.
- Los datos operativos se almacenan fuera del ejecutable y nunca forman parte del paquete ni del repositorio.
- La aplicacion puede instalar nuevas versiones publicadas en GitHub Releases tras verificar SHA-256.

## Privacidad

Este repositorio no contiene bases de datos, hojas de calculo operativas, documentos clinicos, configuraciones locales, logs ni respaldos. La lista de exclusiones y el ensamblado de release bloquean esos formatos.

## Desarrollo

Requiere Windows x64 y Python 3.14.3.

```powershell
& 'C:\Users\ampar\AppData\Local\Programs\Python\Python314\python.exe' -m pip install -r requirements.lock
& 'C:\Users\ampar\AppData\Local\Programs\Python\Python314\python.exe' -m pytest tests
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_release.ps1 -ValidateOnly
```

La entrega completa se genera con:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\build_release.ps1 -AllowUnsigned
```

Para una distribucion formal se debe usar un certificado Authenticode mediante `-SigningCertificateThumbprint`.
