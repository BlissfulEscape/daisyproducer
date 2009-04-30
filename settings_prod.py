from settings_common import *

DEBUG = TEMPLATE_DEBUG = False

DATABASE_ENGINE = 'mysql'
DATABASE_OPTIONS = {
    "default-character-set": "utf8",
    "init_command": "SET storage_engine=INNODB",
}
DATABASE_NAME = 'daisyproducer_prod'
DATABASE_USER = 'daisyproducer'
DATABASE_PASSWORD = ''

DAISY_PIPELINE_PATH = os.path.join('/', 'opt', 'daisy-pipeline')
