from hachoir.parser import createParser
from hachoir.core.tools import makePrintable
from hachoir.metadata import extractMetadata
from hachoir.core.i18n import initLocale
from sys import argv, stderr, exit
from os import walk
from os.path import join as path_join
from fnmatch import fnmatch
import codecs

OUTPUT_FILENAME = "metadata.csv"


class Extractor:

    def __init__(self, directory, fields):
        self.directory = directory
        self.fields = fields
        self.charset = "UTF-8"
        self.total = 0
        self.invalid = 0

    def main(self):
        output = codecs.open(OUTPUT_FILENAME, "w", self.charset)
        for filename in self.findFiles(self.directory, '*.doc'):
            self.total += 1
            line = self.processFile(filename)
            if line:
                print(line, file=output)
            else:
                self.invalid += 1
        output.close()
        self.summary()

    def summary(self):
        print(file=stderr)
        print("Valid files: %s" % (self.total - self.invalid), file=stderr)
        print("Invalid files: %s" % self.invalid, file=stderr)
        print("Total files: %s" % self.total, file=stderr)
        print(file=stderr)
        print("Result written into %s" % OUTPUT_FILENAME, file=stderr)

    def findFiles(self, directory, pattern):
        for dirpath, dirnames, filenames in walk(directory):
            for filename in filenames:
                if not fnmatch(filename.lower(), pattern):
                    continue
                yield path_join(dirpath, filename)

    def processFile(self, filename):
        print("[%s] Process file %s..." % (self.total, filename))
        parser = createParser(filename)
        if not parser:
            print("Unable to parse file", file=stderr)
            return None
        try:
            metadata = extractMetadata(parser)
        except Exception as err:
            print("Metadata extraction error: %s" % str(err), file=stderr)
            return None
        if not metadata:
            print("Unable to extract metadata", file=stderr)
            return None

        filename = makePrintable(filename, self.charset)
        line = [filename]
        for field in self.fields:
            value = metadata.getText(field, '')
            value = makePrintable(value, self.charset)
            line.append(value)
        return '; '.join(line)


def main():
    initLocale()
    if len(argv) != 3:
        print("usage: %s directory fields" % argv[0], file=stderr)
        print(file=stderr)
        print("eg. %s . title,creation_date" % argv[0], file=stderr)
        exit(1)
    directory = argv[1]
    fields = [field.strip() for field in argv[2].split(",")]
    Extractor(directory, fields).main()
