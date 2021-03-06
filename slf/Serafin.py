"""!
Read/Write Serafin files and manipulate associated data
"""

import copy
import logging
import numpy as np
import os
import struct

module_logger = logging.getLogger(__name__)


VARIABLES_2D, VARIABLES_3D = {'fr': {}, 'en': {}}, {'fr': {}, 'en': {}}


def build_variables_table():
    base_folder = os.path.dirname(os.path.realpath(__file__))
    for dic, name in zip([VARIABLES_2D, VARIABLES_3D], ['Serafin_var2D.csv', 'Serafin_var3D.csv']):
        with open(os.path.join(base_folder, 'data', name), 'r') as f:
            f.readline()  # header
            for line in f.readlines():
                var_id, var_name_fr, var_name_en, _ = line.rstrip().split(';')
                dic['fr'][var_name_fr] = var_id
                dic['en'][var_name_en] = var_id

build_variables_table()


class SerafinValidationError(Exception):
    """!
    @brief Custom exception for Serafin file content check
    """
    def __init__(self, message):
        super().__init__(message)
        self.message = message
        module_logger.error('SERAFIN VALIDATION ERROR: %s' % message)


class SerafinRequestError(Exception):
    """!
    @brief Custom exception for requesting invalid values from Serafin object
    """
    def __init__(self, message):
        super().__init__(message)
        self.message = message
        module_logger.error('SERAFIN REQUEST ERROR: %s' % message)


class SerafinHeader:
    """!
    @brief A data type for reading and storing the Serafin file header
    """

    def __init__(self, file, file_size, language):
        self.file_size = file_size
        self.language = language

        # Check if file is empty (usefull if re-runs after a crash)
        if self.file_size == 0:
            raise SerafinValidationError('File is empty (file size is equal to 0)')

        # Read title
        file.read(4)
        self.title = file.read(72)
        self.file_type = file.read(8)
        module_logger.debug('The file type is: "%s"' % self.file_type.decode('utf-8'))
        file.read(4)
        if self.file_type.decode('utf-8') == 'SERAFIND':
            self.float_type = 'd'
            self.float_size = 8
            self.np_float_type = np.float64
        else:
            self.float_type = 'f'
            self.float_size = 4
            self.np_float_type = np.float32

        # Read the number of linear and quadratic variables
        file.read(4)
        self.nb_var = struct.unpack('>i', file.read(4))[0]
        self.nb_var_quadratic = struct.unpack('>i', file.read(4))[0]
        module_logger.debug('The file has %d variables' % self.nb_var)
        file.read(4)
        if self.nb_var_quadratic != 0:
            raise SerafinValidationError('The number of quadratic variables is not equal to zero')

        # Read variable names and units
        self.var_IDs, self.var_names, self.var_units = [], [], []
        for ivar in range(self.nb_var):
            file.read(4)
            self.var_names.append(file.read(16))
            self.var_units.append(file.read(16))
            file.read(4)

        # IPARAM: 10 integers (not all are useful...)
        file.read(4)
        self.params = struct.unpack('>10i', file.read(40))
        file.read(4)
        self.nb_planes = self.params[6]

        self.is_2d = (self.nb_planes == 0)

        if self.params[-1] == 1:
            # Read 6 integers which correspond to simulation starting date
            file.read(4)
            self.date = struct.unpack('>6i', file.read(6 * 4))
            file.read(4)
        else:
            self.date = None

        # 4 very important integers
        file.read(4)
        self.nb_elements = struct.unpack('>i', file.read(4))[0]
        self.nb_nodes = struct.unpack('>i', file.read(4))[0]
        self.nb_nodes_per_elem = struct.unpack('>i', file.read(4))[0]
        test_value = struct.unpack('>i', file.read(4))[0]
        if test_value != 1:
            raise SerafinValidationError('The magic number is not equal to one')
        file.read(4)

        # verify data consistence and determine 2D or 3D
        if self.is_2d:
            if self.nb_nodes_per_elem != 3:
                raise SerafinValidationError('Unknown mesh type')
        else:
            if self.nb_nodes_per_elem != 6:
                raise SerafinValidationError('The number of nodes per element is not equal to 6')
            if self.nb_planes < 2:
                raise SerafinValidationError('The number of planes is less than 2')
        module_logger.debug('The file is determined to be %s' % {True: '2D', False: '3D'}[self.is_2d])

        # determine the number of nodes in 2D
        if self.is_2d:
            self.nb_nodes_2d = self.nb_nodes
        else:
            self.nb_nodes_2d = self.nb_nodes // self.nb_planes

        # IKLE
        file.read(4)
        nb_ikle_values = self.nb_elements * self.nb_nodes_per_elem
        self.ikle = np.array(struct.unpack('>%ii' % nb_ikle_values,
                                           file.read(4 * nb_ikle_values)))
        file.read(4)

        # IPOBO
        file.read(4)
        nb_ipobo_values = '>%ii' % self.nb_nodes
        self.ipobo = np.array(struct.unpack(nb_ipobo_values, file.read(4 * self.nb_nodes)))
        file.read(4)

        # x coordinates
        file.read(4)
        nb_coord_values = '>%i%s' % (self.nb_nodes, self.float_type)
        coord_size = self.nb_nodes * self.float_size
        self.x = np.array(struct.unpack(nb_coord_values, file.read(coord_size)), dtype=self.np_float_type)
        file.read(4)

        # y coordinates
        file.read(4)
        self.y = np.array(struct.unpack(nb_coord_values, file.read(coord_size)), dtype=self.np_float_type)
        file.read(4)

        # Header size
        self.header_size = (80 + 8) + (8 + 8) + (self.nb_var * (8 + 32)) \
                                    + (40 + 8) + (self.params[-1] * ((6 * 4) + 8)) + (16 + 8) \
                                    + (nb_ikle_values * 4 + 8) + (self.nb_nodes * 4 + 8) + 2 * (coord_size + 8)
        # Frame size (all variable values for one time step)
        self.frame_size = 8 + self.float_size + (self.nb_var * (8 + self.nb_nodes * self.float_size))

        # Deduce the number of frames and test the integer division
        self.nb_frames = (self.file_size - self.header_size) // self.frame_size
        module_logger.debug('The file has %d frames of size %d bytes' % (self.nb_frames, self.frame_size))

        if self.nb_frames * self.frame_size != (self.file_size - self.header_size):
            raise SerafinValidationError('Something wrong with the file size (header and frames) check')

        # Deduce variable IDs from names
        var_table = VARIABLES_2D[self.language] if self.is_2d else VARIABLES_3D[language]
        for var_name, var_unit in zip(self.var_names, self.var_units):
            name = var_name.decode(encoding='utf-8').strip()
            if name not in var_table:
                module_logger.warning('WARNING: The variable name "%s" is not known. '
                                      'The complete name will be used as ID' % name)
                var_id = name
            else:
                var_id = var_table[name]
            self.var_IDs.append(var_id)

        # Build ikle2d
        if not self.is_2d:
            ikle = self.ikle.reshape(self.nb_elements, self.nb_nodes_per_elem)
            self.ikle_2d = np.empty([self.nb_elements // (self.nb_planes - 1), 3], dtype=int)
            nb_lines = self.ikle_2d.shape[0]
            # test the integer division
            if nb_lines * (self.nb_planes - 1) != self.nb_elements:
                raise SerafinValidationError('The number of elements is not divisible by (number of planes - 1)')
            for i in range(nb_lines):
                self.ikle_2d[i] = ikle[i, [0, 1, 2]]
        else:
            self.ikle_2d = self.ikle.reshape(self.nb_elements, self.nb_nodes_per_elem)

        module_logger.debug('Finished reading the header')

    def summary(self):
        template = 'The file is of type {} {}. It has {} variable{}{},\non {} nodes and {} elements for {} time frame{}.'
        return template.format(self.file_type.decode('utf-8'),
                               {True: '2D', False: '3D'}[self.is_2d], self.nb_var,
                               '' if self.is_2d else ', %d layers' % self.nb_planes,
                               ['', 's'][self.nb_var > 1], self.nb_nodes, self.nb_elements, self.nb_frames,
                               ['', 's'][self.nb_frames > 1])

    def copy(self):
        return copy.deepcopy(self)

    def is_double_precision(self):
        return self.float_type == 'd'

    def to_single_precision(self):
        self.file_type = bytes('SERAFIN', 'utf-8').ljust(8)
        self.float_type = 'f'
        self.float_size = 4
        self.np_float_type = np.float32

        nb_ikle_values = self.nb_elements * self.nb_nodes_per_elem
        coord_size = self.nb_nodes * self.float_size

        self.header_size = (80 + 8) + (8 + 8) + (self.nb_var * (8 + 32)) \
                                    + (40 + 8) + (self.params[-1] * ((6 * 4) + 8)) + (16 + 8) \
                                    + (nb_ikle_values * 4 + 8) + (self.nb_nodes * 4 + 8) + 2 * (coord_size + 8)
        self.frame_size = 8 + self.float_size + (self.nb_var * (8 + self.nb_nodes * self.float_size))
        self.file_size = self.header_size + self.nb_frames * self.frame_size

    def apply_transform(self, transformations):
        if not transformations:
            return self.copy()
        points = [np.array([x, y, 0]) for x, y in zip(self.x, self.y)]
        for t in transformations:
            points = [t(p) for p in points]
        new_header = self.copy()
        new_header.x = np.array([p[0] for p in points])
        new_header.y = np.array([p[1] for p in points])
        return new_header


class Serafin:
    """!
    @brief A Serafin object corresponds to a single Serafin in file IO stream
    """
    def __init__(self, filename, mode, language):
        self.language = language
        self.mode = mode

        self.file = None  # will be opened when called using 'with'
        self.filename = filename
        self.file_size = None
        self.mode = mode

    def __enter__(self):
        self.file = open(self.filename, self.mode)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.file.close()
        return False


class Read(Serafin):
    """!
    @brief Serafin file input stream
    """
    def __init__(self, filename, language):
        super().__init__(filename, 'rb', language)
        self.header = None
        self.time = []
        self.file_size = os.path.getsize(self.filename)
        module_logger.info('Reading the input file: "%s" of size %d bytes' % (filename, self.file_size))

    def read_header(self):
        """!
        @brief Read the file header and check the file consistency
        """
        self.header = SerafinHeader(self.file, self.file_size, self.language)

    def get_time(self):
        """!
        @brief Read the time in the Serafin file
        """
        module_logger.debug('Reading the time series from the file')
        self.file.seek(self.header.header_size, 0)
        for i in range(self.header.nb_frames):
            self.file.read(4)
            self.time.append(struct.unpack('>%s' % self.header.float_type, self.file.read(self.header.float_size))[0])
            self.file.read(4)
            self.file.seek(self.header.frame_size - 8 - self.header.float_size, 1)

    def _get_var_index(self, var_ID):
        """!
        @brief Handle data request by variable ID
        @param var_ID <str>: the ID of the requested variable
        @return index <int> the index (0-based) of the requested variable
        """
        if self.header is None:
            raise SerafinRequestError('Cannot extract variable from empty list (forgot read_header ?)')
        try:
            index = self.header.var_IDs.index(var_ID)
        except ValueError:
            raise SerafinRequestError('Variable ID %s not found' % var_ID)
        return index

    def read_var_in_frame(self, time_index, var_ID):
        """!
        @brief Read a single variable in a frame
        @param time_index <float>: 0-based index of simulation time from the target frame
        @param var_ID <str>: variable ID
        @return <numpy 1D-array>: values of the variables, of length equal to the number of nodes
        """
        module_logger.debug('Reading variable %s at frame %i' % (var_ID, time_index))
        nb_values = '>%i%s' % (self.header.nb_nodes, self.header.float_type)
        pos_var = self._get_var_index(var_ID)
        self.file.seek(self.header.header_size + time_index * self.header.frame_size
                       + 8 + self.header.float_size + pos_var * (8 + self.header.float_size * self.header.nb_nodes), 0)
        self.file.read(4)
        return np.array(struct.unpack(nb_values, self.file.read(self.header.float_size * self.header.nb_nodes)),
                        dtype=self.header.np_float_type)


class Write(Serafin):
    """!
    @brief Serafin file output stream
    """
    def __init__(self, filename, language):
        super().__init__(filename, 'wb', language)
        module_logger.info('Writing the output file: "%s"' % filename)

    def __enter__(self):
        try:
            return Serafin.__enter__(self)
        except FileExistsError:
            module_logger.error('ERROR: Cannot overwrite existing file')
            raise FileExistsError('File {} already exists (remove the file or change the option '
                                  'and then re-run the program)'.format(self.filename))

    def write_header(self, header):
        """!
        @brief Write Serafin header from attributes
        """
        # Title and file type
        self.file.write(struct.pack('>i', 80))
        self.file.write(header.title)
        self.file.write(header.file_type)
        self.file.write(struct.pack('>i', 80))

        # Number of variables
        self.file.write(struct.pack('>i', 8))
        self.file.write(struct.pack('>i', header.nb_var))
        self.file.write(struct.pack('>i', header.nb_var_quadratic))
        self.file.write(struct.pack('>i', 8))

        # Variable names and units
        for j in range(header.nb_var):
            self.file.write(struct.pack('>i', 2 * 16))
            self.file.write(header.var_names[j].ljust(16))
            self.file.write(header.var_units[j].ljust(16))
            self.file.write(struct.pack('>i', 2 * 16))

        # Date
        self.file.write(struct.pack('>i', 10 * 4))
        self.file.write(struct.pack('>10i', *header.params))
        self.file.write(struct.pack('>i', 10 * 4))
        if header.params[-1] == 1:
            self.file.write(struct.pack('>i', 6 * 4))
            self.file.write(struct.pack('>6i', *header.date))
            self.file.write(struct.pack('>i', 6 * 4))

        # Number of elements, of nodes, of nodes per element and the magic number
        self.file.write(struct.pack('>i', 4 * 4))
        self.file.write(struct.pack('>i', header.nb_elements))
        self.file.write(struct.pack('>i', header.nb_nodes))
        self.file.write(struct.pack('>i', header.nb_nodes_per_elem))
        self.file.write(struct.pack('>i', 1))  # magic number
        self.file.write(struct.pack('>i', 4 * 4))

        # IKLE
        nb_ikle_values = header.nb_elements * header.nb_nodes_per_elem
        self.file.write(struct.pack('>i', 4 * nb_ikle_values))
        nb_val = '>%ii' % nb_ikle_values
        self.file.write(struct.pack(nb_val, *header.ikle))
        self.file.write(struct.pack('>i', 4 * nb_ikle_values))

        # IPOBO
        self.file.write(struct.pack('>i', 4 * header.nb_nodes))
        nb_val = '>%ii' % header.nb_nodes
        self.file.write(struct.pack(nb_val, *header.ipobo))
        self.file.write(struct.pack('>i', 4 * header.nb_nodes))

        # X coordinates
        self.file.write(struct.pack('>i', 4 * header.nb_nodes))
        nb_val = '>%i%s' % (header.nb_nodes, header.float_type)
        self.file.write(struct.pack(nb_val, *header.x))
        self.file.write(struct.pack('>i', 4 * header.nb_nodes))

        # Y coordinates
        self.file.write(struct.pack('>i', 4 * header.nb_nodes))
        nb_val = '>%i%s' % (header.nb_nodes, header.float_type)
        self.file.write(struct.pack(nb_val, *header.y))
        self.file.write(struct.pack('>i', 4 * header.nb_nodes))

    def write_entire_frame(self, header, time_to_write, values):
        """!
        @brief write all variables/nodes values
        @param time_to_write <float>: time in second
        @param values <numpy 2D-array>: values to write, of dimension (nb_var, nb_nodes)
        """
        nb_values = '>%i%s' % (header.nb_nodes, header.float_type)
        self.file.write(struct.pack('>i', 4))
        self.file.write(struct.pack('>%s' % header.float_type, time_to_write))
        self.file.write(struct.pack('>i', 4))

        for i in range(header.nb_var):
            self.file.write(struct.pack('>i', header.float_size * header.nb_nodes))
            self.file.write(struct.pack(nb_values, *values[i, :]))
            self.file.write(struct.pack('>i', header.float_size * header.nb_nodes))

