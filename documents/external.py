import os
import tempfile
import textwrap
import math
from os.path import join, basename, splitext
from pyPdf import PdfFileReader
from shutil import rmtree
from subprocess import call, Popen, PIPE
import re
import zipfile

import libxml2
import libxslt
import louis
from daisyproducer.version import getVersion
from django.conf import settings
from lxml import etree

def filterBrlContractionhints(file_path):
    """Filter all the brl:contractionhints from the given file_path.
    This is done using an XSLT stylesheet. Return the name of a
    temporary file that contains the filtered content. The caller is
    responsible for removing the temporary file."""
    tmpFile = tempfile.NamedTemporaryFile(prefix="daisyproducer-", suffix=".xml", delete=False)
    tmpFile.close() # we are only interested in a unique filename
    command = (
        "xsltproc",
        "--output", tmpFile.name,
        join(settings.PROJECT_DIR, 'documents', 'xslt', 'filterBrlContractionhints.xsl'),
        file_path,
        )
    call(command)
    return tmpFile.name

def filterProcessingInstructions(file_path):
    """Filter all the processing instructions from the given file_path.
    This is done using an XSLT stylesheet. Return the name of a
    temporary file that contains the filtered content. The caller is
    responsible for removing the temporary file."""
    tmpFile = tempfile.NamedTemporaryFile(prefix="daisyproducer-", suffix=".xml", delete=False)
    tmpFile.close() # we are only interested in a unique filename
    command = (
        "xsltproc",
        "--output", tmpFile.name,
        join(settings.PROJECT_DIR, 'documents', 'xslt', 'filterProcessingInstructions.xsl'),
        file_path,
        )
    call(command)
    return tmpFile.name

def generatePDF(inputFile, outputFile, taskscript='DTBookToLaTeX.taskScript', **kwargs):
    tmpDir = tempfile.mkdtemp(prefix="daisyproducer-")
    fileBaseName = splitext(basename(inputFile))[0]
    latexFileName = join(tmpDir, fileBaseName + ".tex")

    # map True and False to "true" and "false"
    kwargs.update([(k, str(v).lower()) for (k, v) in kwargs.iteritems() if isinstance(v, bool)])
        # Transform to LaTeX using pipeline
    command = (
        join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
        join(settings.DAISY_PIPELINE_PATH, 'scripts',
             'create_distribute', 'latex', taskscript),
        "--input=%s" % inputFile,
        "--output=%s" % latexFileName,
        "--fontsize=%(font_size)s" % kwargs,
        "--font=%(font)s" % kwargs,
        "--pageStyle=%(page_style)s" % kwargs,
        "--alignment=%(alignment)s" % kwargs,
        "--stocksize=%(stock_size)s" % kwargs,
        "--line_spacing=%(line_spacing)s" % kwargs,
        "--replace_em_with_quote=%(replace_em_with_quote)s" % kwargs,
        "--paperwidth=%(paperwidth)s" % kwargs if 'paperwidth' in kwargs else None,
        "--paperheight=%(paperheight)s" % kwargs if 'paperheight' in kwargs else None,
        "--left_margin=%(left_margin)s" % kwargs if 'left_margin' in kwargs else None,
        "--right_margin=%(right_margin)s" % kwargs if 'right_margin' in kwargs else None,
        "--top_margin=%(top_margin)s" % kwargs if 'top_margin' in kwargs else None,
        "--bottom_margin=%(bottom_margin)s" % kwargs if 'bottom_margin' in kwargs else None,
        )
    command = filter(None, command) # filter out empty arguments
    call(command)
    # Transform to pdf using xelatex
    pdfFileName = join(tmpDir, fileBaseName + ".pdf")
    currentDir = os.getcwd()
    os.chdir(tmpDir)
    command = (
        "xelatex",
        "-halt-on-error",
        latexFileName,
        )
    call(command)
    call(command) # call LaTeX again to make sure the toc is inserted
    os.rename(pdfFileName, outputFile)
    os.chdir(currentDir)
    rmtree(tmpDir)

def zipDirectory(directory, zipFileName, document_title):
    outputFile = zipfile.ZipFile(zipFileName, 'w')
    cwd = os.getcwd()
    os.chdir(directory)
    for dirpath, dirnames, filenames in os.walk('.'):
        for filename in filenames:
            # zipFile support in Python has a few weak spots: Older
            # Pythons die if the filename or the arcname that is
            # passed to ZipFile.write is not in the right encoding
            # FIXME: remove the encode("latin-1") workaround once we
            # upgrade to 2.6.2
            outputFile.write(
                os.path.join(dirpath, filename).encode("latin-1"), 
                os.path.join(document_title, dirpath, filename).encode("latin-1"))
    outputFile.close()
    os.chdir(cwd)

class DaisyPipeline:

    @staticmethod
    def validate(file_path):
        """Validate a given file_path using the Validator from the Daisy
        Pipeline. Return an empty string if the validation was
        successful. Return a list of error messages as delivered by
        the Daisy Pipeline otherwise."""

        xmlschema = etree.XMLSchema(file=join(settings.PROJECT_DIR, 'documents', 'schema', 'minimalSchema.xsd'))
        etree.clear_error_log()
        try:
            doc = etree.parse(file_path)
        except etree.XMLSyntaxError, e:
            entries = e.error_log.filter_from_level(etree.ErrorLevels.FATAL)
            return [("%s on line %s" % (entry.message, entry.line)) for entry in entries]

        if not xmlschema.validate(doc):
            entries = xmlschema.error_log
            return [("%s on line %s" % (entry.message, entry.line)) for entry in entries]

        tmpFile = filterBrlContractionhints(file_path)
        command = (
            join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
            # FIXME: This requires a version of the pipeline from
            # trunk (>= rev 2480). You could argue that it is
            # pointless to check for a DOCTYPE declaration here as the
            # filterBrlContractionhints above adds it _anyway_. Well
            # let's just leave it in here in case the filter code ever
            # is refactored out.
            join(settings.DAISY_PIPELINE_PATH, 'scripts', 'verify',
                 'ConfigurableValidator.taskScript'),
            "--validatorInputFile=%s" % tmpFile,
            # # also check using schematron tests
            # "--validatorInputSchemas=%s" % "-//TPB//SCH dtbook 2005 Narrator//EN",
            # # make sure it has to be a DTBook file
            # "--validatorRequireInputType=%s" % "Dtbook document",
            # # make sure files with a missing DOCTYPE declaration do
            # # not validate. 
            "--validatorInputDelegates=%s" %
            "org.daisy.util.fileset.validation.delegate.impl.NoDocTypeDeclarationDelegate",
            )
        result = map(lambda line: line.replace("file:%s" % file_path, "", 1),
                   map(lambda line: line.replace("[ERROR, Validator]", "", 1), 
                       filter(lambda line: line.find('[ERROR, Validator]') != -1, 
                              Popen(command, stdout=PIPE).communicate()[0].splitlines())))
        os.remove(tmpFile)
        return result
        
    @staticmethod
    def dtbook2pdf(inputFile, outputFile, **kwargs):
        """Transform a dtbook xml file to pdf"""
        tmpFile = filterBrlContractionhints(inputFile)

        generatePDF(tmpFile, outputFile, **kwargs)
        os.remove(tmpFile)

    @staticmethod
    def dtbook2xhtml(inputFile, outputFile, **kwargs):
        """Transform a dtbook xml file to xhtml"""
        tmpFile = filterBrlContractionhints(inputFile)
        # map True and False to "true" and "false"
        kwargs.update([(k, str(v).lower()) for (k, v) in kwargs.iteritems() if isinstance(v, bool)])
        command = (
            join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
            join(settings.DAISY_PIPELINE_PATH, 'scripts',
                 'create_distribute', 'xhtml', 'DtbookToXhtml.taskScript'),
            "--input=%s" % tmpFile,
            "--output=%s" % outputFile,
            )
        for k, v in kwargs.iteritems():
            command += ("--%s=%s" % (k,v),)
        call(command)
        os.remove(tmpFile)

    @staticmethod
    def dtbook2rtf(inputFile, outputFile, **kwargs):
        """Transform a dtbook xml file to rtf"""
        tmpFile = filterBrlContractionhints(inputFile)
        # map True and False to "true" and "false"
        kwargs.update([(k, str(v).lower()) for (k, v) in kwargs.iteritems() if isinstance(v, bool)])
        command = (
            join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
            join(settings.DAISY_PIPELINE_PATH, 'scripts',
                 'create_distribute', 'text', 'DtbookToRtf.taskScript'),
            "--input=%s" % tmpFile,
            "--output=%s" % outputFile,
            )
        for k, v in kwargs.iteritems():
            command += ("--%s=%s" % (k,v),)
        call(command)
        os.remove(tmpFile)

    @staticmethod
    def dtbook2epub(inputFile, outputFile, **kwargs):
        """Transform a dtbook xml file to EPUB"""
        tmpFile = filterBrlContractionhints(inputFile)
        command = (
            join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
            join(settings.DAISY_PIPELINE_PATH, 'scripts',
                 'create_distribute', 'epub', 'OPSCreator.taskScript'),
            "--input=%s" % tmpFile,
            "--output=%s" % outputFile,
            )
        for k, v in kwargs.iteritems():
            value = v.encode('utf8') if isinstance(v, str) or isinstance(v, unicode) else v
            command += ("--%s=%s" % (k,value),)
        call(command)
        os.remove(tmpFile)

    @staticmethod
    def dtbook2text_only_fileset(inputFile, outputPath, **kwargs):
        """Transform a dtbook xml file to a Daisy 2.02 Text-Only fileset"""
        tmpFile = filterBrlContractionhints(inputFile)
        # map True and False to "true" and "false"
        kwargs.update([(k, str(v).lower()) for (k, v) in kwargs.iteritems() if isinstance(v, bool)])
        command = (
            join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
            join(settings.DAISY_PIPELINE_PATH, 'scripts',
                 'create_distribute', 'dtb', 'Fileset-DtbookToDaisy202TextOnly.taskScript'),
            "--input=%s" % tmpFile,
            "--outputPath=%s" % outputPath,
            )
        for k, v in kwargs.iteritems():
            command += ("--%s=%s" % (k,v),)
        call(command)
        os.remove(tmpFile)

    @staticmethod
    def dtbook2text_only_dtb(inputFile, outputPath, **kwargs):
        """Transform a dtbook xml file to a Daisy 3 Text-Only"""
        tmpFile = filterBrlContractionhints(inputFile)
        tmpFile2 = filterProcessingInstructions(tmpFile)
        # map True and False to "true" and "false"
        kwargs.update([(k, str(v).lower()) for (k, v) in kwargs.iteritems() if isinstance(v, bool)])
        command = (
            join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
            join(settings.DAISY_PIPELINE_PATH, 'scripts',
                 'create_distribute', 'dtb', 'DTBookToDaisy3TextOnlyDTB.taskScript'),
            "--input=%s" % tmpFile2,
            "--outputPath=%s" % outputPath,
            )
        for k, v in kwargs.iteritems():
            command += ("--%s=%s" % (k,v),)
        fnull = open(os.devnull, 'w')
        result = map(lambda line: line.strip(),
                     map(lambda line: line.replace("[ERROR, Validator]", "", 1), 
                         filter(lambda line: line.find('[ERROR, Validator]') != -1, 
                                Popen(command, stdout=PIPE, stderr=fnull).communicate()[0].splitlines())))
        fnull.close()
        os.remove(tmpFile)
        os.remove(tmpFile2)
        return result

    @staticmethod
    def dtbook2dtb(inputFile, outputPath, **kwargs):
        """Transform a dtbook xml file to a Daisy Full-Text Full-Audio book"""
        tmpFile = filterBrlContractionhints(inputFile)
        # map True and False to "true" and "false"
        kwargs.update([(k, str(v).lower()) for (k, v) in kwargs.iteritems() if isinstance(v, bool)])
        command = (
            join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
            join(settings.DAISY_PIPELINE_PATH, 'scripts',
                 'create_distribute', 'dtb', 'Narrator-DtbookToDaisy.taskScript'),
            "--input=%s" % tmpFile,
            "--outputPath=%s" % outputPath,
            )
        for k, v in kwargs.iteritems():
            command += ("--%s=%s" % (k,v),)
        call(command)
        os.remove(tmpFile)

class StandardLargePrint:

    PAGES_PER_VOLUME=200

    PARAMETER_DEFAULTS = {
        'font_size': '17pt',
        'font': 'Tiresias LPfont',
        'page_style': 'plain',
        'alignment': 'left',
        'stock_size': 'a4paper',
        'line_spacing': 'onehalfspacing',
        'paperwidth': '200mm',
        'paperheight': '250mm',
        'left_margin': '28mm',
        'right_margin': '20mm',
        'top_margin': '20mm',
        'bottom_margin': '20mm',
        'replace_em_with_quote': 'true',
        }

    @staticmethod
    def insertVolumeSplitPoints(file_path, number_of_volumes):
        tmpFile = tempfile.NamedTemporaryFile(prefix="daisyproducer-", suffix=".xml", delete=False)
        tmpFile.close()
        command = (
            join(settings.DAISY_PIPELINE_PATH, 'pipeline.sh'),
            join(settings.DAISY_PIPELINE_PATH, 'scripts',
                 'modify_improve', 'dtbook', 'DTBookVolumeSplit.taskScript'),
            "--input=%s" % file_path,
            "--output=%s" % tmpFile.name,
            "--number_of_volumes=%s" % number_of_volumes,
            )
        call(command)
        return tmpFile.name

    @staticmethod
    def determineNumberOfVolumes(file_path, **kwargs):
        pdfFile = tempfile.NamedTemporaryFile(prefix="daisyproducer-", suffix=".pdf")
        generatePDF(file_path, pdfFile.name, **kwargs)
        pdfReader = PdfFileReader(file(pdfFile.name, "rb"))
        volumes = int(math.ceil(pdfReader.getNumPages() / float(StandardLargePrint.PAGES_PER_VOLUME)))
        pdfFile.close()
        return volumes

    @staticmethod
    def dtbook2pdf(inputFile, outputFile, **kwargs):
        """Transform a dtbook xml file to pdf"""
        tmpFile = filterBrlContractionhints(inputFile)
        defaults = StandardLargePrint.PARAMETER_DEFAULTS.copy()
        defaults.update(kwargs)
        numberOfVolumes =  StandardLargePrint.determineNumberOfVolumes(tmpFile, **defaults)
        tmpFile2 = StandardLargePrint.insertVolumeSplitPoints(tmpFile, numberOfVolumes)

        generatePDF(tmpFile2, outputFile, **defaults)
        os.remove(tmpFile)
        os.remove(tmpFile2)
        

class Liblouis:

    contractionMap = {
        0 : 'de-ch-g0.utb', 
        1 : 'de-ch-g1.ctb', 
        2 : 'de-ch-g2.ctb'}

    yesNoMap = {
        True : "yes", 
        False : "no" }

    @staticmethod
    def dtbook2brl(inputFile, outputFile, **kwargs):
        """Transform a dtbook xml file to brl"""
        tmpFile = filterBrlContractionhints(inputFile)
        # prepare xml input for liblouis
        command = (
            "xsltproc",
            join(settings.PROJECT_DIR, 'documents', 'xslt', 'brailleSanitize.xsl'),
            tmpFile,
            )
        p1 = Popen(command, stdout=PIPE)
        # transform to braille
        command = (
            "xml2brl",
            "-CcellsPerLine=%(cells_per_line)s" % kwargs,
            "-ClinesPerPage=%(lines_per_page)s" % kwargs,
            "-CliteraryTextTable=%s" % Liblouis.contractionMap[kwargs['contraction']],
            "-Chyphenate=%s" % Liblouis.yesNoMap[kwargs['hyphenation']],
            "-CprintPages=%s" % Liblouis.yesNoMap[kwargs['show_original_page_numbers']],
            "-Cinterpoint=no",
            "-CnewEntries=no",
            "-Cinterline=no",
            "-CinputTextEncoding=utf8",
            "-CoutputEncoding=ascii8",
            "-CbraillePageNumberAt=bottom",
            "-CprintPageNumberAt=top",
            "-CbeginningPageNumber=1",
            "-Cparagraphs=yes",
            "-CbraillePages=yes",
            "-CfileEnd=\"^z\"",
            # FIXME: find a solution on how to pass these values
            # r"-CpageEnd=\f",
            # r"-ClineEnd=\n",
            "-CsemanticFiles=dtbook.sem",
            "-CinternetAccess=no",
            )
        f = open(outputFile, 'w')
        p2 = Popen(command, stdin=p1.stdout, stdout=f, 
                   # FIXME: xml2brl creates a temporary file in cwd,
                   # so we have to change directory to a place where
                   # www-data can create temporary files
                   cwd=tempfile.gettempdir())
        p2.communicate()
        f.close()
        os.remove(tmpFile)


class SBSForm:

    @staticmethod
    def dtbook2sbsform(inputFile, outputFile, **kwargs):
        """Transform a dtbook xml file to sbsform"""
        hyphenate = kwargs.get('hyphenation', False)
        hyphenator = (
            "java",
            "-jar", join(settings.EXTERNAL_PATH, 'dtbook_hyphenator', 'dtbook_hyphenator.jar'),
            inputFile,
            )
        translator = (
            join(settings.EXTERNAL_PATH, 'dtbook2sbsform', 'dtbook2sbsform.sh'),
            "-s:-" if hyphenate else "-s:%s" % inputFile,
            )
        kwargs["version"] = getVersion()
        for k, v in kwargs.iteritems():
            if isinstance(v, bool):
                # map True and False to "true()" and "false()"
                translator += ("?%s=%s" % (k, "true()" if v else "false()"),)
            elif isinstance(v, int):
                translator += ("?%s=%s" % (k, v),)
            else:
                translator += ("%s=%s" % (k,v),)
        f = open(outputFile, 'w')
        env = {'LANG': 'en_US.UTF-8'}
        if hyphenate:
            p1 = Popen(hyphenator, stdout=PIPE, env=env)
            p2 = Popen(translator, stdin=p1.stdout, stdout=f, env=env)
        else:
            p2 = Popen(translator, stdout=f)
        p2.communicate()
        f.close()
