"""!
Flux calculations across sections
"""


import numpy as np

from slf.interpolation import Interpolator
from slf.mesh2D import Mesh2D


class TriangularVectorField(Mesh2D):
    """!
    @brief The representation of Mesh2D in Serafin file when one computes the flux across sections of some vectors

    The integral of scalars along a line can also be computed.

    The flux across a section (or integral along a line) is the sum of the flux (or integral) on
    all intersected segments between the mesh and the section.
    """
    def __init__(self, input_header, construct_index):
        super().__init__(input_header, construct_index)

    def section_intersection(self, section):
        """!
        @brief Return the intersections (normal vectors and interpolators) of the mesh with a open polyline
        @param section <geom.geometry.Polyline>: An open polyline
        @return <dict>: The list of tuples (normal vector, interpolator) of every intersected segments in triangles
        """
        intersections = {}
        potential_elements = self.get_intersecting_elements(section.bounds())
        for i, j, k in potential_elements:
            t = self.triangles[i, j, k]
            is_intersected, t_intersections = section.linestring_intersection(t)
            if is_intersected:
                interpolator = Interpolator(t)
                intersections[i, j, k] = []
                for intersection in t_intersections:
                    line = []   # the list of tuple (normal_vector, interpolator) for all start/end/turning points
                    prev_x, prev_y = None, None
                    for x, y in intersection.coords:
                        if prev_x is None:  # the first point doesn't have a normal vector
                            prev_x, prev_y = x, y
                            line.append(([0, 0], interpolator.get_interpolator_at(x, y)))
                        else:
                            line.append(([prev_y-y, x-prev_x],
                                        interpolator.get_interpolator_at(x, y)))
                    intersections[i, j, k].append(line)
        return intersections

    @staticmethod
    def line_integral(intersections, scalar_flux_values):
        """!
        @brief The line integral of a scalar field along a line (not really a flux)
        """
        flux = 0
        for i, j, k in intersections:  # iterating through triangles in the intersection
            f_vals = scalar_flux_values[[i, j, k]]

            for endpoints in intersections[i, j, k]:
                endpoints_f = []

                for normal, interpolator in endpoints:  # pre-compute the values on each start/turning/end points
                    endpoints_f.append(interpolator.dot(f_vals))

                for p in range(len(endpoints)-1):  # iterating through intersecting segments inside the triangle
                    flux += (endpoints_f[p] + endpoints_f[p+1]) * np.linalg.norm(endpoints[p+1][0])
        return flux / 2

    @staticmethod
    def line_double_integral(intersections, height_values, scalar_flux_values):
        """!
        @brief The line integral of a scalar field (product of two scalars) across a section (not really a flux)
        """
        flux = 0
        for i, j, k in intersections:  # iterating through triangles in the intersection
            h_vals = height_values[[i, j, k]]
            f_vals = scalar_flux_values[[i, j, k]]

            for endpoints in intersections[i, j, k]:
                endpoints_h, endpoints_f = [], []

                for normal, interpolator in endpoints:  # pre-compute the values on each start/turning/end points
                    endpoints_h.append(interpolator.dot(h_vals))
                    endpoints_f.append(interpolator.dot(f_vals))

                for p in range(len(endpoints)-1):  # iterating through intersecting segments inside the triangle
                    first_h, second_h = endpoints_h[p], endpoints_h[p+1]
                    first_f, second_f = endpoints_f[p], endpoints_f[p+1]

                    flux += (2 * (first_f * first_h + second_f * second_h)
                               + (first_f * second_h + second_f * first_h)) * np.linalg.norm(endpoints[p+1][0])

        return flux / 6

    @staticmethod
    def line_flux(intersections, x_vector_values, y_vector_values):
        """!
        @brief The flux of a vector field across a line
        """
        flux = 0
        for i, j, k in intersections:  # iterating through triangles in the intersection
            x_vals = x_vector_values[[i, j, k]]
            y_vals = y_vector_values[[i, j, k]]

            for endpoints in intersections[i, j, k]:
                endpoints_x, endpoints_y = [], []

                for normal, interpolator in endpoints:  # pre-compute the values on each start/turning/end points
                    endpoints_x.append(interpolator.dot(x_vals))
                    endpoints_y.append(interpolator.dot(y_vals))

                for p in range(len(endpoints)-1):  # iterating through intersecting segments inside the triangle
                    normal = endpoints[p+1][0]

                    first_normal = np.dot([endpoints_x[p], endpoints_y[p]], normal)
                    second_normal = np.dot([endpoints_x[p+1], endpoints_y[p+1]], normal)

                    flux += first_normal + second_normal

        return flux / 2

    @staticmethod
    def area_flux(intersections, x_vector_values, y_vector_values, height_values):
        """!
        @brief The flux of a vector field across a section (the surface height is a scalar field)
        """
        flux = 0
        for i, j, k in intersections:  # iterating through triangles in the intersection
            x_vals = x_vector_values[[i, j, k]]
            y_vals = y_vector_values[[i, j, k]]
            h_vals = height_values[[i, j, k]]

            for endpoints in intersections[i, j, k]:
                endpoints_x, endpoints_y, endpoints_h = [], [], []

                for normal, interpolator in endpoints:  # pre-compute the values on each start/turning/end points
                    endpoints_x.append(interpolator.dot(x_vals))
                    endpoints_y.append(interpolator.dot(y_vals))
                    endpoints_h.append(interpolator.dot(h_vals))

                for p in range(len(endpoints)-1):  # iterating through intersecting segments inside the triangle
                    normal = endpoints[p+1][0]

                    first_normal = np.dot([endpoints_x[p], endpoints_y[p]], normal)
                    second_normal = np.dot([endpoints_x[p+1], endpoints_y[p+1]], normal)

                    first_h, second_h = endpoints_h[p], endpoints_h[p+1]

                    flux += 2 * (first_normal * first_h + second_normal * second_h) \
                              + (first_normal * second_h + second_normal * first_h)

        return flux / 6

    @staticmethod
    def mass_flux(intersections, x_vector_values, y_vector_values, height_values, density_values):
        """!
        @brief The mass-flux of a vector field across a section (with surface height and density, two scalars fields)
        """
        flux = 0
        for i, j, k in intersections:  # iterating through triangles in the intersection
            x_vals = x_vector_values[[i, j, k]]
            y_vals = y_vector_values[[i, j, k]]
            h_vals = height_values[[i, j, k]]
            d_vals = density_values[[i, j, k]]

            for endpoints in intersections[i, j, k]:
                endpoints_x, endpoints_y, endpoints_h, endpoints_d = [], [], [], []

                for normal, interpolator in endpoints:  # pre-compute the values on each start/turning/end points
                    endpoints_x.append(interpolator.dot(x_vals))
                    endpoints_y.append(interpolator.dot(y_vals))
                    endpoints_h.append(interpolator.dot(h_vals))
                    endpoints_d.append(interpolator.dot(d_vals))

                for p in range(len(endpoints)-1):  # iterating through intersecting segments inside the triangle
                    normal = endpoints[p+1][0]

                    first_normal = np.dot([endpoints_x[p], endpoints_y[p]], normal)
                    second_normal = np.dot([endpoints_x[p+1], endpoints_y[p+1]], normal)

                    first_h, second_h = endpoints_h[p], endpoints_h[p+1]
                    first_d, second_d = endpoints_d[p], endpoints_d[p+1]

                    flux += 9 * (first_normal * first_h * first_d + second_normal * second_h * second_d) + \
                            (2*first_normal+second_normal) * (2*first_h+second_h) * (2*first_d+second_d) + \
                            (first_normal+2*second_normal) * (first_h+2*second_h) * (first_d+2*second_d)

        return flux / 72


class FluxCalculator:
    """!
    Compute flux across sections (integral along lines) from a Serafin input stream
    """

    LINE_INTEGRAL, DOUBLE_LINE_INTEGRAL, LINE_FLUX, AREA_FLUX, MASS_FLUX = 0, 1, 2, 3, 4

    def __init__(self, flux_type, var_IDs, input_stream, section_names, sections, time_sampling_frequency):
        self.flux_type = flux_type
        self.input_stream = input_stream
        self.section_names = section_names
        self.sections = sections

        self.var_IDs = var_IDs

        self.time_indices = range(0, len(input_stream.time), time_sampling_frequency)

        self.mesh = None
        self.intersections = []

    def construct_triangles(self):
        self.mesh = TriangularVectorField(self.input_stream.header, True)

    def construct_intersections(self):
        """!
        Construct the intersections between the mesh and all input sections
        """
        for section in self.sections:
            self.intersections.append(self.mesh.section_intersection(section))

    def flux_in_frame(self, intersections, values):
        """!
        @brief Do the flux computation in a single frame, depending on the flux type
        @param values <numpy.1D-array>: The values of the scalar/vector fields
        @return <float>: The value of the flux
        """
        if self.flux_type == FluxCalculator.LINE_INTEGRAL:
            return TriangularVectorField.line_integral(intersections, values[0])
        elif self.flux_type == FluxCalculator.DOUBLE_LINE_INTEGRAL:
            return TriangularVectorField.line_double_integral(intersections, values[0], values[1])
        elif self.flux_type == FluxCalculator.LINE_FLUX:
            return TriangularVectorField.line_flux(intersections, values[0], values[1])
        elif self.flux_type == FluxCalculator.AREA_FLUX:
            return TriangularVectorField.area_flux(intersections, values[0], values[1], values[2])
        else:
            return TriangularVectorField.mass_flux(intersections, values[0], values[1], values[2], values[3])

    def run(self, format_string='{0:.6f}'):
        """!
        Separate the major part of the computation, allowing a GUI override
        """
        result = []
        for time_index in self.time_indices:
            i_result = [str(self.input_stream.time[time_index])]
            values = []
            for var_ID in self.var_IDs:
                values.append(self.input_stream.read_var_in_frame(time_index, var_ID))

            for j in range(len(self.sections)):
                intersections = self.intersections[j]
                flux = self.flux_in_frame(intersections, values)
                i_result.append(format_string.format(flux))
            result.append(i_result)
        return result

    def write_csv(self, result, output_stream, separator):
        output_stream.write('time')
        for name in self.section_names:
            output_stream.write(separator)
            output_stream.write(name)
        output_stream.write('\n')

        for line in result:
            output_stream.write(separator.join(line))
            output_stream.write('\n')
