import os

from celery.schedules import crontab

SECRET_KEY = os.environ["SUPERSET_SECRET_KEY"]

SQLALCHEMY_DATABASE_URI = (
    "postgresql+psycopg2://"
    f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    "@postgres:5432/superset"
)

# permite conectar o Superset ao mesmo servidor Postgres do desafio
PREVENT_UNSAFE_DB_CONNECTIONS = False

# ---------------------------------------------------------------
# Desafio 2 (RF18): alertas e relatorios. Executados pelo Celery nos servicos superset-worker e
# superset-beat (perfil "alertas"); o e-mail vai para o Mailpit, um SMTP ficticio com caixa de
# entrada em http://localhost:8025. Sem o perfil no ar, o Superset funciona normalmente e os
# alertas ficam configurados, mas nao sao avaliados.
# ---------------------------------------------------------------

FEATURE_FLAGS = {"ALERT_REPORTS": True}

REDIS_URL = "redis://redis:6379/0"


class CeleryConfig:  # pylint: disable=too-few-public-methods
    broker_url = REDIS_URL
    result_backend = REDIS_URL
    imports = ("superset.sql_lab", "superset.tasks.scheduler")
    worker_prefetch_multiplier = 1
    task_acks_late = False
    beat_schedule = {
        "reports.scheduler": {"task": "reports.scheduler", "schedule": crontab(minute="*", hour="*")},
        "reports.prune_log": {"task": "reports.prune_log", "schedule": crontab(minute=0, hour=0)},
    }


CELERY_CONFIG = CeleryConfig

# o worker busca os dados do grafico do alerta pela API do proprio Superset
WEBDRIVER_BASEURL = "http://superset:8088/"
WEBDRIVER_BASEURL_USER_FRIENDLY = f"http://localhost:{os.environ.get('SUPERSET_HOST_PORT', '8088')}/"

SMTP_HOST = "mailpit"
SMTP_PORT = 1025
SMTP_STARTTLS = False
SMTP_SSL = False
SMTP_USER = ""
SMTP_PASSWORD = ""
SMTP_MAIL_FROM = "alertas@plataforma.example"
ALERT_REPORTS_NOTIFICATION_DRY_RUN = False

# numeros e datas no formato brasileiro (graficos e tabelas)
D3_FORMAT = {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["R$ ", ""]}
D3_TIME_FORMAT = {
    "dateTime": "%A, %e de %B de %Y. %X", "date": "%d/%m/%Y", "time": "%H:%M:%S", "periods": ["AM", "PM"],
    "days": ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"],
    "shortDays": ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"],
    "months": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
               "outubro", "novembro", "dezembro"],
    "shortMonths": ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"],
}
