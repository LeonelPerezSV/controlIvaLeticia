from sqlalchemy import inspect, text


def ensure_schema(engine):
    """Apply tiny additive migrations needed by this self-contained Streamlit app.
    Safe for fresh PostgreSQL/SQLite installs and existing databases from earlier app builds.
    """
    insp = inspect(engine)
    if 'rent_withholdings' not in insp.get_table_names():
        return
    cols = {c['name'] for c in insp.get_columns('rent_withholdings')}
    additions = {
        'cefafa': 'NUMERIC(14,2) DEFAULT 0',
        'bienestar_magisterial': 'NUMERIC(14,2) DEFAULT 0',
        'isss_ivm': 'NUMERIC(14,2) DEFAULT 0',
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in cols:
                conn.execute(text(f'ALTER TABLE rent_withholdings ADD COLUMN {name} {ddl}'))
