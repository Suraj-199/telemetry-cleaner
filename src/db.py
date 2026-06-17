import sqlite3
import os
import json
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'telemetry_platform.db')

@contextmanager
def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Platform detection rules
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS platform_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            platform TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
        ''')
        
        # Network normalization mappings
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS network_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_value TEXT NOT NULL UNIQUE,
            normalized_value TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
        ''')
        
        # Metric normalization mappings
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS metric_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_metric TEXT NOT NULL,
            platform TEXT,
            normalized_metric TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            UNIQUE(source_metric, platform)
        )
        ''')
        
        # Trace prefix rules
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS trace_prefix_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prefix TEXT NOT NULL UNIQUE,
            active INTEGER DEFAULT 1
        )
        ''')
        
        # Report configurations
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS report_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            group_by TEXT NOT NULL,
            statistics TEXT NOT NULL,
            filters TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        )
        ''')
        
        # Uploads tracking
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_size INTEGER,
            sheets_found TEXT,
            total_records INTEGER,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            processed_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
        ''')
        
        # Generated reports metadata
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id INTEGER,
            upload_id INTEGER,
            filename TEXT,
            record_count INTEGER,
            status TEXT DEFAULT 'generating',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (config_id) REFERENCES report_configs(id),
            FOREIGN KEY (upload_id) REFERENCES uploads(id)
        )
        ''')
        
        conn.commit()

        # Seed initial data if tables are empty
        seed_data(cursor)
        conn.commit()

def seed_data(cursor):
    # Check if we need to seed platform rules
    cursor.execute('SELECT COUNT(*) FROM platform_rules')
    if cursor.fetchone()[0] == 0:
        platform_data = [
            ('Consumer Android', 'Android', 10),
            ('Consumer iOS', 'iOS', 10),
            ('Android', 'Android', 1),
            ('iOS', 'iOS', 1)
        ]
        cursor.executemany('INSERT INTO platform_rules (pattern, platform, priority) VALUES (?, ?, ?)', platform_data)

    # Check if we need to seed network mappings
    cursor.execute('SELECT COUNT(*) FROM network_mappings')
    if cursor.fetchone()[0] == 0:
        network_data = [
            ('WIFI', 'wifi'), ('LTE', 'lte'), ('HSPA', 'hspa'), ('HSDPA', 'hsdpa'),
            ('EDGE', 'edge'), ('GPRS', 'gprs'), ('CDMA', 'cdma'), ('UMTS', 'umts'),
            ('NR', '5g'), ('[MISSING]', 'undefined'), ('UNKNOWN', 'undefined')
        ]
        cursor.executemany('INSERT INTO network_mappings (source_value, normalized_value) VALUES (?, ?)', network_data)

    # Check if we need to seed metric mappings
    cursor.execute('SELECT COUNT(*) FROM metric_mappings')
    if cursor.fetchone()[0] == 0:
        metric_data = [
            ('total_load_ms', 'Android', 'total_ms'),
            ('repo_fetch_ms', 'Android', 'repo_fetch'),
            ('api_total_ms', 'Android', 'total_api'),
            ('render_ms', 'Android', 'render_ms'),
            ('json_deserialization_ms', 'Android', 'json_deserialisation'),
            ('template_parsing_ms', 'Android', 'template_parsing'),
            ('total_time_ms', 'iOS', 'total_ms'),
            ('repo_fetch_time_ms', 'iOS', 'repo_fetch'),
            ('api_total', 'iOS', 'total_api'),
            ('render_time_ms', 'iOS', 'render_ms'),
            ('duration_ms', None, 'duration_ms') # Applies to any platform if specified without one
        ]
        cursor.executemany('INSERT INTO metric_mappings (source_metric, platform, normalized_metric) VALUES (?, ?, ?)', metric_data)

    # Check if we need to seed trace prefixes
    cursor.execute('SELECT COUNT(*) FROM trace_prefix_rules')
    if cursor.fetchone()[0] == 0:
        # User requested not to drop prefixes, so we leave this empty
        pass

    # Check if we need to seed default report config
    cursor.execute('SELECT COUNT(*) FROM report_configs')
    if cursor.fetchone()[0] == 0:
        default_config = (
            'Default Screen Performance',
            'Screen Performance by Platform & Network',
            json.dumps(['normalized_trace_name', 'platform', 'network_type']),
            json.dumps(['p75', 'p90']),
            json.dumps({})
        )
        cursor.execute('''
            INSERT INTO report_configs (name, description, group_by, statistics, filters) 
            VALUES (?, ?, ?, ?, ?)
        ''', default_config)


# Utility functions to fetch rules
def get_platform_rules():
    with get_db_connection() as conn:
        return conn.execute('SELECT * FROM platform_rules WHERE active=1 ORDER BY priority DESC').fetchall()

def get_network_mappings():
    with get_db_connection() as conn:
        return {row['source_value']: row['normalized_value'] for row in conn.execute('SELECT * FROM network_mappings WHERE active=1')}

def get_metric_mappings():
    with get_db_connection() as conn:
        mappings = {}
        for row in conn.execute('SELECT * FROM metric_mappings WHERE active=1'):
            key = (row['source_metric'], row['platform'])
            mappings[key] = row['normalized_metric']
            if row['platform'] is None:
                mappings[(row['source_metric'], 'ALL')] = row['normalized_metric']
        return mappings

def get_trace_prefixes():
    with get_db_connection() as conn:
        return [row['prefix'] for row in conn.execute('SELECT * FROM trace_prefix_rules WHERE active=1')]
    
def get_report_configs():
     with get_db_connection() as conn:
        return conn.execute('SELECT * FROM report_configs WHERE active=1').fetchall()
