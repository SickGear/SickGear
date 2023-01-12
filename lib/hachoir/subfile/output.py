from hachoir.stream import FileOutputStream, StreamError
from hachoir.core.error import error
from errno import EEXIST
from os import mkdir, path


class Output:
    """
    Store files found by search tool.
    """

    def __init__(self, directory):
        self.directory = directory
        self.mkdir = False
        self.file_id = 1

    def createDirectory(self):
        try:
            mkdir(self.directory)
        except OSError as err:
            if err.errno == EEXIST:
                pass
            else:
                raise

    def createFilename(self, file_ext=None):
        filename = "file-%04u" % self.file_id
        self.file_id += 1
        if file_ext:
            filename += file_ext
        return filename

    def writeFile(self, filename, stream, offset, size):
        # Create directory (only on first call)
        if not self.mkdir:
            self.createDirectory()
            self.mkdir = True

        # Create output file
        filename = path.join(self.directory, filename)
        output = FileOutputStream(filename)

        # Write output
        try:
            output.copyBytesFrom(stream, offset, size // 8)
        except StreamError as err:
            error("copyBytesFrom() error: %s" % err)
        return filename
