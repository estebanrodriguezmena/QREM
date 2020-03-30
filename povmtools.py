# -*- coding: utf-8 -*-
"""
Created on Fri Feb 23 02:08:17 2018

@author: Filip Maciejewski

email: filip.b.maciejewski@gmail.com
"""
import cmath as c
import numpy as np
import math
import ancillary_functions as anf
import qiskit
from enum import Enum
from typing import List
import copy
import itertools

epsilon = 10 ** (-7)


class PauliEigenkets(Enum):
    ZERO = 0,
    ONE = 3,
    X_PLUS = 1,
    Y_PLUS = 2,
    X_MINUS = 4,
    Y_MINUS = 5


def get_pauli_eigenket(z):
    if z == PauliEigenkets.ZERO:
        state = np.array([1, 0]).reshape(2, 1)
    elif z == PauliEigenkets.ONE:
        state = np.array([0, 1]).reshape(2, 1)
    elif z == PauliEigenkets.X_PLUS:
        state = (1 / c.sqrt(2) * np.array([1, 1])).reshape(2, 1)
    elif z == PauliEigenkets.Y_PLUS:
        state = (1 / c.sqrt(2) * np.array([1, 1j])).reshape(2, 1)
    elif z == PauliEigenkets.X_MINUS:
        state = (1 / c.sqrt(2) * np.array([1, - 1])).reshape(2, 1)
    elif z == PauliEigenkets.Y_MINUS:
        state = (1 / c.sqrt(2) * np.array([1, - 1j])).reshape(2, 1)
    else:
        raise ValueError(f'Wrong state index. Expected: 0 - 5. Got: {z}.')
    return state


pauli_probe_eigenkets = [
    get_pauli_eigenket(PauliEigenkets.ZERO),
    get_pauli_eigenket(PauliEigenkets.ONE),
    get_pauli_eigenket(PauliEigenkets.X_PLUS),
    get_pauli_eigenket(PauliEigenkets.X_MINUS),
    get_pauli_eigenket(PauliEigenkets.Y_PLUS),
    get_pauli_eigenket(PauliEigenkets.Y_MINUS)
]


def check_if_projector_is_in_computational_basis(projector, d=2):
    n = int(math.log(np.shape(projector)[0], d))
    computational_basis_projectors = computational_projectors(d, n)

    for base_projector in computational_basis_projectors:
        projectors_difference = base_projector - projector  # independent from global phase
        norm = np.linalg.norm(projectors_difference)
        if abs(norm) < epsilon:
            return True

    return False


def computational_projectors(d, n=1):
    return [get_density_matrix(computational_basis(d, n)[i]) for i in range(d ** n)]


def computational_basis(d, n=1):
    m_d = d ** n
    eye = np.eye(m_d)
    return [np.array(eye[:, i]).reshape(m_d, 1) for i in range(m_d)]


def get_density_matrix(ket):
    return ket @ ket_to_bra(ket)


def ket_to_bra(ket):
    bra = np.matrix.getH(ket)
    return bra


def euler_angles_1q(unitary_matrix):
    # TODO FBM: This is slightly modified copied qiskit function
    _CUTOFF_PRECISION = 10 ** (-7)

    """Compute Euler angles for a single-qubit gate.

    Find angles (theta, phi, lambda) such that
    unitary_matrix = phase * Rz(phi) * Ry(theta) * Rz(lambda)

    Args:
        unitary_matrix (ndarray): 2x2 unitary matrix

    Returns:
        tuple: (theta, phi, lambda) Euler angles of SU(2)

    Raises:
        QiskitError: if unitary_matrix not 2x2, or failure
    """
    if unitary_matrix.shape != (2, 2):
        raise ValueError("euler_angles_1q: expected 2x2 matrix")

    import scipy.linalg as la
    phase = la.det(unitary_matrix) ** (-1.0 / 2.0)
    U = phase * unitary_matrix  # U in SU(2)
    # OpenQASM SU(2) parameterization:
    # U[0, 0] = exp(-i(phi+lambda)/2) * cos(theta/2)
    # U[0, 1] = -exp(-i(phi-lambda)/2) * sin(theta/2)
    # U[1, 0] = exp(i(phi-lambda)/2) * sin(theta/2)
    # U[1, 1] = exp(i(phi+lambda)/2) * cos(theta/2)
    theta = 2 * math.atan2(abs(U[1, 0]), abs(U[0, 0]))

    # Find phi and lambda
    phiplambda = 2 * np.angle(U[1, 1])
    phimlambda = 2 * np.angle(U[1, 0])
    phi = (phiplambda + phimlambda) / 2.0
    lamb = (phiplambda - phimlambda) / 2.0

    # Check the solution
    Rzphi = np.array([[np.exp(-1j * phi / 2.0), 0],
                      [0, np.exp(1j * phi / 2.0)]], dtype=complex)
    Rytheta = np.array([[np.cos(theta / 2.0), -np.sin(theta / 2.0)],
                        [np.sin(theta / 2.0), np.cos(theta / 2.0)]], dtype=complex)
    Rzlambda = np.array([[np.exp(-1j * lamb / 2.0), 0],
                         [0, np.exp(1j * lamb / 2.0)]], dtype=complex)
    V = np.dot(Rzphi, np.dot(Rytheta, Rzlambda))
    if la.norm(V - U) > _CUTOFF_PRECISION:
        raise ValueError("compiling.euler_angles_1q incorrect result norm(V-U)={}".
                         format(la.norm(V - U)))
    return theta, phi, lamb


def get_su2_parametrizing_angles(m_a):
    # Get three angles theta, phi, lambda which parametrize single-qubit unitary from SU(2)

    if is_pauli_x(m_a):
        return ['x']
    elif anf.identity_check(m_a):
        return ['id']

    m_a = anf.thresh(m_a)
    eps_angles = 10 ** (-7)
    determinant = np.linalg.det(m_a)
    delta = c.phase(determinant) / 2
    m_a = c.exp(-1j * delta) * m_a

    euler_theta_phi_lambda = qiskit.quantum_info.synthesis.euler_angles_1q(m_a)

    angles = [euler_theta_phi_lambda[0], euler_theta_phi_lambda[1], euler_theta_phi_lambda[2]]

    for i in range(0, 3):
        if abs(angles[i]) < eps_angles:
            angles[i] = 0

    return angles


def is_pauli_x(m_a):
    return True if anf.zero_check(m_a - anf.pauli_sigmas['X']) else False


# prepare unitaries which are to be implemented to change computational basis initial state of qubits (assuming
# |0000...0> initial state) for chosen probe states. Here we assume perfect qubit initialization.
def get_unitary_change_ket_qubit(ket):
    state = get_density_matrix(ket)
    if check_if_projector_is_in_computational_basis(state):
        if state[0][0] == 1:
            return np.eye(2)
        elif state[1][1] == 1:
            return anf.pauli_sigmas["X"]
        else:
            raise ValueError('error')
    else:
        U = np.zeros((2, 2), dtype=complex)
        U[:, 0] = ket[:, 0]
        ket_comp = np.array([[1], [0]]).reshape(2, 1)
        ket_perp = ket_comp - np.vdot(ket_comp, ket) * ket
        ket_perp = ket_perp / np.linalg.norm(ket_perp)
        U[:, 1] = ket_perp[:, 0]

        determinant = np.linalg.det(U)
        delta = c.phase(determinant) / 2

        U = c.exp(-1j * delta) * U

        return U


def calculate_total_variation_distance(p: np.array, q: np.array) -> float:
    """
    Description:
        Given two vectors calculate Total-Variation distance between them. See Refs. [1] and [2] for the relation
        between TV-distance and operational distance between quantum measurements.

    Parameters:
        :param p: numpy vector
        :param q: numpy vector

    Returns:
         Total variation distance between vectors q and p.
    """

    return np.linalg.norm(p - q, ord=1) / 2

# Done
def get_off_diagonal_from_matrix(matrix: np.ndarray) -> np.ndarray:
    """
    Description:
        Calculates and returns off-diagonal part of given matrix.
    Parameters:
        :param matrix: Matrix for which off-diagonal part shall be calculated.
    Return:
        Off-diagonal part of the matrix.
    """
    matrix_dimension = matrix.shape[0]
    matrix_off_diagonal = copy.copy(matrix)

    for i in range(matrix_dimension):
        # set diagonal element to zero
        matrix_off_diagonal[i, i] = 0

    return matrix_off_diagonal


# Done
def get_off_diagonal_povm_part(povm: List[np.ndarray]) -> List[np.ndarray]:
    """
    Description:
        Get the off-diagonal part of each of POVM's effects.

    Parameters:
        :param povm: POVM - list of matrices representing POVM's effects.

    Return:
        List of np.ndarrays representing off-diagonal parts of POVM's effects.
    """

    # implement function get_off_diagonal_from_matrix for each effect Mi in povm
    return [get_off_diagonal_from_matrix(Mi) for Mi in povm]


def get_diagonal_povm_part(povm: List[np.ndarray]) -> List[np.ndarray]:
    """
    Description:
        From given povm get only diagonal part as a list.

    Parameters:
        :param povm: A POVM from effects of which diagonal parts shall be extracted.

    Return:
        List of numpy arrays representing diagonal parts of given POVM.
    """
    return [np.diagflat(np.diag(effect)) for effect in povm]


def is_valid_probability_vector(examined_vector: List[float], threshold=1e-5) -> bool:
    """
    Description:
        Checks if given vector is valid probability vector i.e. has only positive values that sums to 1.

    Parameters:
        :param examined_vector: Vector of probabilities for which the validity is checked.
        :param threshold: Error threshold when determining probabilities sum condition.

    Returns:
        Information whether  is a valid probability vector or not.
    """
    values_sum = 0

    for value in examined_vector:
        if value < 0:
            return False
        values_sum += value

    return abs(values_sum - 1) < threshold


def find_closest_prob_vector(quasiprobability_vector: List[float]) -> List[float]:
    """
    Description:
        Given quasiprobability vector (here it means: vector which elements sum up to 1 but some of them are
        negative), find the closest probability vector in Euclidean norm (2-norm). Here we use fast algorithm from
        Ref. [4] and use the fact that probability distributions are special case of quantum states (namely,
        diagonal quantum states) and fact that for diagonal matrices 2-norm between them is the same as 2-norm
        between vectors created from their diagonal elements.

    Parameters:
        :param quasiprobability_vector: Quasiprobability vector for which closest probability vector will be found.

    Returns:
        Probability vector closest to quasiprobability_vector in Euclidean norm.
    """

    if isinstance(quasiprobability_vector, list):
        d = len(quasiprobability_vector)
    elif isinstance(quasiprobability_vector, type(np.array(0))):
        d = quasiprobability_vector.shape[0]

    # format vector properly
    # TODO: we probably don't need it here
    quasiprobability_vector = np.array(quasiprobability_vector).reshape(d, 1)

    # copy part of the vector
    p000 = list(quasiprobability_vector[:, 0])

    # For algorithm to work we need to rearrange probability vector elements, so we need to keep track of their
    # initial ordering
    p1 = [[i, p000[i]] for i in range(d)]

    # Sort elements in descending order
    p1_sorted = sorted(p1, reverse=True, key=lambda x: x[1])

    # Initiate accumulator
    a = 0

    # go from the i=d
    for i in np.arange(0, d)[::-1]:

        # get vector element
        mu_i = p1_sorted[i][1]

        # if mu_i +a/(i+1) is negative, do the following:
        if mu_i + a / (i + 1) < 0:
            # add mu_i to accumulator
            a += mu_i

            # set vector element to 0
            p1_sorted[i][1] = 0
        # otherwise
        else:
            # update proper elements of probability vector
            for j in range(i + 1):
                p1_sorted[j][1] += a / (i + 1)
            # finish algorithm - everything is positive now
            break

    # return to initial order
    ordered_p = sorted(p1_sorted, key=lambda x: x[0])

    # get rid of indices
    p_good_format = [ordered_p[i][1] for i in range(d)]

    return p_good_format


def permute_matrix(matrix, n, transposition):
    # Swap qubits (subspaces) in 2**n dimensional matrix
    # n - number of qubits
    # transposition - which qubits to SWAP.
    # IMPORTANT: in transposition they are numbered from 1

    swap = qubit_swap(n, transposition)
    return swap @ matrix @ swap


def qubit_swap(n, transposition=(1, 1)):
    # create swap between two qubits in 2**n dimensional space
    # labels inside transpositions start from 1.

    D = 2 ** n
    # renumerate for Python convention
    i, j = transposition[0] - 1, transposition[1] - 1

    names = [(bin(j)[2:].zfill(n)) for j in list(range(2 ** n))]

    new_names = copy.copy(names)
    # exchange classical register bits with labels in transposition
    # this defines new order in classical register which respects qubit SWAP
    for k in range(len(new_names)):
        string = list(new_names[k])
        string[i], string[j] = string[j], string[i]
        new_names[k] = ''.join([s for s in string])

    transformation = np.eye(D)

    for x in range(len(names)):
        bit = int(new_names[x], 2)

        # if we need to change the bit, let's do this
        if bit != x:
            transformation[x, x] = 0
            transformation[bit, bit] = 0
            transformation[bit, x] = 1
            transformation[x, bit] = 1

    return transformation


def reorder_classical_register(new_order):
    # reorder classical register according to new_order.
    n = len(new_order)

    # get standard classical register
    standard_register = [(bin(j)[2:].zfill(n)) for j in list(range(2 ** n))]

    return [sort_bitstring(s, new_order) for s in standard_register]


def sort_things(stuff_to_sort, according_to_what):
    # Sort stuff according to some other stuff assuming that the stuff_to_sort is sorted in natural order (0, 1, 2, ...)
    X = copy.copy(according_to_what)
    Y = copy.copy(stuff_to_sort)

    return [x for _, x in sorted(zip(X, Y), key=lambda pair: pair[0])]


def sort_bitstring(string, new_order):
    # sort bits in string according to new_order
    sorted_string = sort_things(list(string), new_order)

    return ''.join([s for s in sorted_string])

def reorder_probabilities(probabilities, new_order):
    # sort elements of probabilities vector according to new_order defined for bits

    D = len(probabilities)
    array_format = False
    if isinstance(probabilities, np.ndarray):
        probabilities = probabilities.reshape(D, 1)
        array_format = True

        # get classical register according sorted to new order
    new_classical_register = reorder_classical_register(new_order)
    # sort probabilities entries according to new register
    sorted_probs = sort_things(probabilities, new_classical_register)

    if array_format:
        return np.array(sorted_probs).reshape(D, 1)
    else:
        return sorted_probs


def get_CBT_norm(J,n,m,rev=False):
    #Get completely bounded trace norm of Choi-matrix J representing quantum channel from n-dimensional space to m-dimensional space
    J=cvx.matrix(J)    
    prob= pic.Problem(verbose=0)    
    X=prob.add_variable("X", (n*m,n*m),vtype='complex')
    
    I = pic.new_param('I',np.eye(m))

    
    rho0=prob.add_variable("rho0",(n,n),vtype='hermitian')
    rho1=prob.add_variable("rho1",(n,n),vtype='hermitian')
    prob.add_constraint(rho0>>0)
    prob.add_constraint(rho1>>0)
    
    prob.add_constraint(pic.trace(rho0)==1)
    prob.add_constraint(pic.trace(rho1)==1)
    
    
    if(rev==True):
        #TODO FBM: test which conention is good.
        #TODO FBM: add reference to paper
        
        #This is convention REVERSED with respect to the paper,
        #and seems that this is a proper one????
        C0=pic.kron(rho0,I)
        C1=pic.kron(rho1,I)
    else:
        C0=pic.kron(I,rho0)
        C1=pic.kron(I,rho1)

    F=pic.trace((J.H)*X)+pic.trace(J*(X.H))


    
    prob.add_constraint(((C0 & X) // (X.H & C1))>>0 )

    prob.set_objective('max',F)
    

    prob.solve(verbose = 0)
        
    if prob.status.count("optimal") > 0:
    #        print('solution optimal')
        1
    elif(prob.status.count("optimal")==0):
        print('uknown_if_solution_optimal')
    
    else:
        print('solution not found')

    cbt_norm=prob.obj_value()/2

    if(abs(np.imag(cbt_norm))>=0.00001):
        raise ValueError
    else:
        cbt_norm=np.real(cbt_norm)

    return cbt_norm
    
    
def get_POVM_choi(POVM):       
    #get Choi matrix of POVM channel
    d=POVM[0].shape[0]
    n=len(POVM)
    J=np.zeros((n*d,n*d),dtype=complex)

    for i in range(n):
        J[i*d:(i+1)*d,i*d:(i+1)*d]=(POVM[i].T)[:,:]        
    
    return J
        
    
    
    
def operational_distance_POVMs(M,P,method='direct'):
    m=len(M)

    difference=([M[i]-P[i] for i in range(m)])
    

    if(method=='CBTN'):
        #this calculates completely bounded trace norm of the channel which is the upper bound for operational distance
        n=M[0].shape[0]        
        J=get_POVM_choi(difference)      
        cbt_norm=get_CBT_norm(J,n,m)
        
        return cbt_norm/2

        
    elif(method=='direct'):     
        #calculate operational distance directly via bruteforce search over subsets of outcomes
        biggest_norm=0
        for k in list(range(m))[::-1]:
            current_list=list(itertools.combinations(difference, k+1))      

            for l in current_list:
                current_sum=sum(l)
                current_norm=np.linalg.norm(current_sum,ord=2)

                if(current_norm>biggest_norm):
                    biggest_norm=current_norm                   

        return biggest_norm







def calculate_statistical_error_bound(number_of_measurement_outcomes: int,
                                      number_of_samples: int,
                                      statistical_error_mistake_probability: float) -> float:
        """
        Description:
            Get upper bound for tv-distance of estimated probability distribution from ideal one. See Ref. [3] for details.

        Parameters:
            :param number_of_measurement_outcomes: number of outcomes, it is the dimension of Hilber space for projective measurement in standard basis
            :param number_of_samples: number of samples for the experiment
            :param statistical_error_mistake_probability: probability for which upper bound might be violated

        Return:
            Statistical error upper bound in total variance distance.
        """



        if number_of_measurement_outcomes < 16:
            # for small number of outcomes "-2" factor is not negligible
            return np.sqrt(
                (np.log(2 ** number_of_measurement_outcomes - 2)
                 - np.log(statistical_error_mistake_probability)) / 2 / number_of_samples
            )
            # for high number of outcomes "-2" factor is negligible
        else:
            return np.sqrt(
                (number_of_measurement_outcomes * np.log(2) - np.log(
                    statistical_error_mistake_probability)) / 2 / number_of_samples
            )








