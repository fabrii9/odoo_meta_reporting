# -*- coding: utf-8 -*-
{
    'name': 'Meta Ads Reporting → BigQuery',
    'version': '16.0.1.0.0',
    'summary': 'Orquestador ETL de Meta Ads a BigQuery con Looker Studio',
    'description': """
        Módulo para extraer métricas de Meta Marketing API,
        procesarlas e insertarlas en BigQuery de forma incremental.
        Odoo funciona como panel de administración, scheduler y gestor de credenciales.
        Looker Studio se conecta directamente a BigQuery para reporting.
    """,
    'author': 'Fabrizio + ChatGPT',
    'license': 'AGPL-3',
    'category': 'Marketing',
    'depends': ['base', 'mail', 'web'],
    'data': [
        'security/meta_ads_security.xml',
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/meta_ads_dataset_views.xml',
        'views/meta_ads_account_views.xml',
        'views/meta_ads_sync_log_views.xml',
        'views/meta_ads_dashboard.xml',
        'views/wizard_views.xml',
    ],
    'external_dependencies': {
        'python': [
            'facebook_business',
            'google.cloud.bigquery',
            'requests',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
