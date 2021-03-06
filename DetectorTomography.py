"""
Created on Wed Aug  8 21:40:15 2018
@author: Filip Maciejewski
email: filip.b.maciejewski@gmail.com

References:
[1] Z. Hradil, J. Řeháček, J. Fiurášek, and M. Ježek, “3 maximum-likelihood methods in quantum mechanics,” in Quantum
State Estimation, edited by M. Paris and J. Řeháček (Springer Berlin Heidelberg, Berlin, Heidelberg, 2004) pp. 59–112.
[2] J. Fiurášek, Physical Review A 64, 024102 (2001), arXiv:quant-ph/0101027 [quant-ph].
"""

import numpy as np
import scipy as sc
import copy
from math import log

from povmtools import get_density_matrix, permute_matrix, reorder_classical_register, sort_things
from qiskit.result import Result
from typing import List
from qiskit_utilities import get_frequencies_array_from_results

from PyMaLi.GeneralTensorCalculator import GeneralTensorCalculator


# GTC stands for General Tensor Calculator.
def gtc_tensor_counting_function(arguments: list):
    result = 1

    for a in arguments:
        result = np.kron(result, a)

    return result


def gtc_matrix_product_counting_function(arguments: list):
    result = arguments[0]

    i = 1

    while i < len(arguments):
        result = result @ arguments[i]
        i += 1

    return result


class QDTCalibrationSetup:
    """
        This class contains information required by DetectorTomographyFitter object to properly calculate
        maximum-likelihood POVM. This class shouldn't have any accessible methods and should only store and transfer
        data to the DetectorTomographyFitter class instances.
    """
    def __init__(self, qubits_number: int, probe_kets: List[np.array], frequencies_array: np.ndarray):
        """
        Description:
            This is default constructor for QDTCalibrationSetup objects. It requires all necessary information, that is
            later used in the QDT process using DetectorTomographyFitter object.
        :param qubits_number: Number of qubits used in the circuits.
        :param probe_kets: Kets upon which circuits were build.
        :param frequencies_array: Results of circuits execution presented as frequencies.
        """
        self.qubits_number = qubits_number
        self.probe_kets = probe_kets
        self.probe_states = self.__get_probe_states(qubits_number, probe_kets)
        self.frequencies_array = frequencies_array

    @classmethod
    def from_qiskit_results(cls, results_list: List[Result], probe_kets: List[np.array]):
        """
        Description:
            This method generates Calibration setup objects directly from qiskit job results and probe kets used
            to generate circuits for these jobs. This method should be interpreted as sort of additional constructor
            for qiskit users.
        :param results_list: List of qiskit jobs results. In case of single job result it should still be a list.
        :param probe_kets: Prove kets (in form of list of np.arrays) used to generate calibration circuits.
        :return: Instance of QDT calibration setup from given job.
        """
        frequencies_array = get_frequencies_array_from_results(results_list)
        # This qubits_number calculation is a little elaborate, but necessary.
        circuits_number = sum(len(results.results) for results in results_list)
        qubits_number = int(log(circuits_number, len(probe_kets)))
        return cls(qubits_number, probe_kets, frequencies_array)

    @staticmethod
    def __get_probe_states(qubits_number: int, probe_kets: List[np.array]) -> List[np.ndarray]:
        """
        Description:
            This method generates probe states (density matrix) from results and kets
            passed to maximum likelihood POVM counting object.
        Parameters:
            :param qubits_number: Number of qubits used in the calibration experiments.
            :param probe_kets: Kets on which job circuits were based.
        Returns:
            List of probe states. These are supposed to have dimension equal to the size of Hilbert space, hence if one
            have used tensor products of single-qubit states, then one needs to give here those tensor products. Order
            needs to fit this of results.results.
        """

        probe_states = []

        for i in range(qubits_number):
            probe_states.append([get_density_matrix(ket) for ket in probe_kets])

        general_tensor_calculator = GeneralTensorCalculator(gtc_tensor_counting_function)

        return general_tensor_calculator.calculate_tensor_to_increasing_list(probe_states)


class DetectorTomographyFitter:
    """
        This class is meant to resemble qiskit's state tomography and process tomography fitters and to calculate the
        maximum likelihood povm estimator describing a detector basing on QDT job results and used probe states.
    """

    def __init__(self, algorithm_convergence_threshold=1e-6):
        self.algorithmConvergenceThreshold = algorithm_convergence_threshold

    def get_maximum_likelihood_povm_estimator(self, calibration_setup: QDTCalibrationSetup) -> List[np.ndarray]:
        """
        Description:
            Given results of Quantum Detector Tomography experiments and list of probe states, return the Maximum
            Likelihood estimation of POVM describing a detector. Uses recursive method from [1]. See also [2].
        Parameters:
            :param calibration_setup: QDTCalibrationSetup object that consists data upon which maximum likelihood POVM
            estimator should be calculated.
        Returns
            Maximum likelihood estimator of POVM describing a detector.
        """

        number_of_probe_states = calibration_setup.frequencies_array.shape[1]
        dimension = calibration_setup.probe_states[0].shape[0]

        povm = []

        for j in range(number_of_probe_states):
            povm.append(np.identity(dimension) / number_of_probe_states)

        # Threshold is dynamic, thus another variable
        threshold = self.algorithmConvergenceThreshold

        i = 0
        current_difference = 1
        while abs(current_difference) >= threshold:
            i += 1

            if i % 50 == 0:
                last_step_povm = copy.copy(povm)

            r_matrices = [self.__get_r_operator(povm[j], j, calibration_setup.frequencies_array,
                                                calibration_setup.probe_states)
                          for j in range(number_of_probe_states)]
            lagrange_matrix = self.__get_lagrange_matrix(r_matrices, povm)
            povm = [self.__calculate_symmetric_m(lagrange_matrix, r_matrices[j], povm[j])
                    for j in range(number_of_probe_states)]

            if i % 50 == 0:  # calculate the convergence test only sometimes to make the code faster
                current_difference = sum([np.linalg.norm(povm[k] - last_step_povm[k], ord=2)
                                          for k in range(number_of_probe_states)])

            elif i > 5e5:  # make sure it does not take too long, sometimes convergence might not be so good
                threshold = 1e-3

            elif i > 1e5:  # make sure it does not take too long, sometimes convergence might not be so good
                threshold = 1e-4

        return povm

    @staticmethod
    def __get_r_operator(m_m: np.ndarray, index_of_povm_effect: int, frequencies_array: np.ndarray,
                         probe_states: List[np.ndarray]) -> np.ndarray:
        """
        Description:
            This method calculates R operator as defined in Ref. [1].
        Parameters:
            :param m_m: Effect for which R operator is calculated.
            :param index_of_povm_effect: Index of povm effect for which R is calculated.
            :param frequencies_array: frequencies_array - array with size (m x n), where m means number of probe states,
            n means number of POSSIBLE outcomes.
            :param probe_states: A list of probe states density matrices.
        Returns:
            The R operator as described in Ref. [1].
        """

        number_of_probe_states = frequencies_array.shape[0]

        d = probe_states[0].shape[0]

        m_r = np.zeros((d, d), dtype=complex)

        for probe_state_index in range(number_of_probe_states):
            expectation_value_on_probe_state = np.trace(m_m @ probe_states[probe_state_index])

            if expectation_value_on_probe_state == 0j:
                continue

            x = frequencies_array[probe_state_index, index_of_povm_effect] / expectation_value_on_probe_state
            m_r += x * probe_states[probe_state_index]

        if np.linalg.norm(m_r) == 0:
            m_r = np.zeros((d, d), dtype=complex)

        return m_r

    @staticmethod
    def __get_lagrange_matrix(r_matrices: List[np.ndarray], povms: List[np.ndarray]) -> np.ndarray:
        """
        Description:
            Calculates Lagrange matrix used in Lagrange multipliers optimization method.
        Parameters:
            :param r_matrices: A list of R matrices described in a method generating them.
            :param povms: A list of effects for which Lagrange matrix will be calculated.
        Returns:
           Lagrange matrix for given parameters.
        """
        number_of_povms = len(povms)
        dimension = povms[0].shape[0]
        second_power_of_lagrange_matrix = np.zeros((dimension, dimension), dtype=complex)

        for j in range(number_of_povms):
            second_power_of_lagrange_matrix += r_matrices[j] @ povms[j] @ r_matrices[j]

        lagrange_matrix = sc.linalg.sqrtm(second_power_of_lagrange_matrix)

        return lagrange_matrix

    @staticmethod
    def __calculate_symmetric_m(m_lagrange_matrix: np.ndarray, m_r: np.ndarray, m_m: np.ndarray) -> np.ndarray:
        """
        Description:
            A method used for calculating symmetric m matrix.
        Parameters:
            :param m_m: A matrix of which symmetric version will be calculated.
            :param m_r: Previously calculated R operator.
            :param m_lagrange_matrix:
        Returns:
            Symmetric m matrix.
        """
        try:
            # Try to perform inversion of lagrange matrix.
            m_inversed_lagrange_matrix = np.linalg.inv(m_lagrange_matrix)
        except np.linalg.LinAlgError:
            # In some special cases it may fail. Provide identity matrix in that scenario.
            m_inversed_lagrange_matrix = np.eye(np.shape(m_lagrange_matrix)[0])

        symmetric_m = m_inversed_lagrange_matrix @ m_r @ m_m @ m_r @ m_inversed_lagrange_matrix

        return symmetric_m


# TODO TR: This method may need to be revisited and possibly reduced into several smaller ones.
def join_povms(povms: List[List[np.ndarray]], qubit_indices_lists: List[List[int]]) -> List[np.ndarray]:
    """
    Description:
        Generates a POVM from given list of POVMs and qubit indices.
    Parameter:
        :param povms: List of POVMs corresponding to qubits indices.
        :param qubit_indices_lists: Indices of qubits for which POVMs were calculated.
    Return:
        POVM describing whole detector.
    """
    qubits_num = sum([len(indices) for indices in qubit_indices_lists])

    swapped_povms = []

    for i in range(len(qubit_indices_lists)):
        indices_now = qubit_indices_lists[i]
        povm_now = povms[i]

        # extend povm to higher-dimensional space.by multiplying by complementing identity from right
        povm_now_extended = [np.kron(Mi, np.eye(2 ** (qubits_num - len(indices_now)))) for Mi in povm_now]

        # begin swapping
        swapped_povm = copy.copy(povm_now_extended)

        # go from back to ensure commuting
        for j in range(len(indices_now))[::-1]:
            index_qubit_now = indices_now[j]

            if index_qubit_now != j:
                # swap qubit from jth position to proper position
                swapped_povm = [permute_matrix(Mj, qubits_num, (j + 1, index_qubit_now + 1)) for Mj in swapped_povm]

        swapped_povms.append(swapped_povm)

    # With POVMs now represented by proper matrices (that is, parts corresponding to adequate qubits are now in
    # desired places), we want to join them.
    general_tensor_calculator = GeneralTensorCalculator(gtc_matrix_product_counting_function)
    povm = general_tensor_calculator.calculate_tensor_to_increasing_list(swapped_povms)

    # We've obtained a POVM, but it is still ordered according to qubit indices. We want to undo that.
    indices_order = []
    for indices_list in qubit_indices_lists:
        indices_order = indices_order + indices_list

    new_classical_register = reorder_classical_register(indices_order)
    sorted_povm = sort_things(povm, new_classical_register)

    return sorted_povm
