# IVA SV

Aplicación web multiempresa para control fiscal mensual de IVA y retenciones de renta en El Salvador.

## Alcance actual
- Multiempresa y períodos mensuales.
- CRUD de empresas, terceros, compras/ventas y retenciones mientras el período aplicable no esté declarado.
- Bloqueo de movimientos cuando F-07/F-14 se marcan declarados.
- Compras y ventas: CCF, CF, NC, ND, FSE y FEX.
- Importación masiva de JSON DTE y prevención de duplicados por código de generación.
- Libros IVA en Excel y PDF.
- CSV F-07 V14: Anexos 1, 2, 3 y 5.
- CSV F-14 V16: 23 columnas A-W, sin encabezados, incluyendo CEFAFA, Bienestar Magisterial, ISSS IVM y período MMYYYY.
- Expediente de declaraciones con adjuntos.
- PostgreSQL mediante `DATABASE_URL`.

## Referencias fiscales incorporadas
- Manual de Usuario para carga de archivos de anexos F-07 V14 — enero 2025.
- Manual de Usuario del anexo de retenciones F-14 V16 — octubre 2025.

## Variables de entorno

```bash
DATABASE_URL=postgresql+psycopg://usuario:clave@host:5432/base
APP_USER=admin
APP_PASSWORD_SHA256=<sha256 de su contraseña>
```

Para generar SHA256:

```python
import hashlib
print(hashlib.sha256('SuClave'.encode()).hexdigest())
```

## Ejecutar localmente

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Producción

1. Cree una base PostgreSQL (Neon, Supabase, Railway u otro proveedor).
2. Configure `DATABASE_URL`, `APP_USER` y `APP_PASSWORD_SHA256` como variables/secrets.
3. Publique el proyecto en GitHub.
4. Despliegue en Streamlit Community Cloud usando `app.py` como archivo principal.

## Regla de cierre fiscal

Mientras el período esté abierto se permite crear, consultar, modificar y eliminar registros. Al marcar F-07 o F-14 como declarado, los movimientos cubiertos por esa declaración quedan bloqueados. Una corrección posterior debe documentarse mediante el mecanismo fiscal correspondiente (nuevo documento/ajuste o declaración modificatoria) sin alterar silenciosamente el histórico declarado.


## Nota para Streamlit Community Cloud

El paquete interno se llama `iva_core` para evitar conflicto con el archivo principal `app.py`.
El archivo principal del despliegue debe ser exactamente `app.py`.

Si usa PostgreSQL en Streamlit Cloud, configure en **Settings > Secrets**:

```toml
DATABASE_URL = "postgresql+psycopg://usuario:clave@host:5432/base"
APP_USER = "admin"
APP_PASSWORD_SHA256 = "<sha256>"
```
