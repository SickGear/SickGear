from hachoir.metadata.metadata import extractMetadata  # noqa

# Just import the module,
# each module use registerExtractor() method
# upstream also imports archive, file_system, misc and program here, their parsers are not loaded
import hachoir.metadata.audio  # noqa
import hachoir.metadata.image  # noqa
import hachoir.metadata.jpeg  # noqa
import hachoir.metadata.riff  # noqa
import hachoir.metadata.video  # noqa
import hachoir.metadata.cr2 # noqa
