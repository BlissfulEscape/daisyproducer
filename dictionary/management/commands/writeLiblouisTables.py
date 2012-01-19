from daisyproducer.dictionary.brailleTables import writeWhiteListTables, writeLocalTables, writeWordSplitTable
from daisyproducer.dictionary.models import Word
from daisyproducer.documents.models import Document
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    args = ''
    help = 'Write Liblouis tables from the confirmed words in the dictionary'

    def handle(self, *args, **options):
        # write new global white lists
        writeWhiteListTables(Word.objects.filter(isConfirmed=True).filter(isLocal=False).order_by('untranslated'))
        # update local tables
        writeLocalTables(Document.objects.all())
        # write new word split table
        writeWordSplitTable(Word.objects.filter(isConfirmed=True).filter(isLocal=False).filter(use_for_word_splitting=True).order_by('untranslated'))
