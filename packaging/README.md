# Empaquetado 4.1

## Entorno reproducible

El release se construye con Windows x64, Python 3.14.3 y las versiones exactas de `requirements.lock`.

```powershell
& 'C:\Users\ampar\AppData\Local\Programs\Python\Python314\python.exe' `
  -m pip install -r requirements.lock
```

Antes de compilar, valide dependencias, firmas, activos, sintaxis y pruebas:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\build_release.ps1 -ValidateOnly
```

## Release firmado

El certificado de firma debe estar en `Cert:\CurrentUser\My`. No se guarda ningun certificado ni clave privada en este proyecto.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\build_release.ps1 `
  -SigningCertificateThumbprint '<HUELLA_SHA1>'
```

Para una entrega interna sin certificado, la ausencia de firma debe aceptarse de forma explicita:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\packaging\build_release.ps1 -AllowUnsigned
```

El resultado se crea en `release/GENERADOR_DE_HOJAS_4.1.2` y en su archivo ZIP. Ambos incluyen comprobaciones SHA-256.

## Regla de privacidad

El ensamblado usa una lista cerrada. Solo admite el ejecutable, notas de version, avisos legales, licencias y hashes. La presencia de una base SQLite, Excel, CSV, JSON operativo o log detiene la entrega.

Nunca use `ENTREGA GENERADOR 4.0` como origen de un release: esa carpeta historica contiene datos operativos.
