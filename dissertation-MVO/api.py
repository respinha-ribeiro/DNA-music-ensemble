
from __future__ import division

import subprocess

import time
from Bio import AlignIO
from Bio import Phylo
from Bio import SeqIO
from Bio import motifs
from Bio.Align import AlignInfo, MultipleSeqAlignment

from Bio.Align.Applications import ClustalwCommandline
from Bio.Align.Applications import MafftCommandline
from Bio.Align.Applications import MuscleCommandline


from scipy.stats import itemfreq

import numpy as np

import datasketch as dk
import pandas as pd

import os
import sys
import random

from Bio.Phylo.TreeConstruction import DistanceCalculator

from matplotlib import pyplot as plt

from music21 import note, scale, instrument, stream, duration, tempo
from music21.instrument import StringInstrument, WoodwindInstrument, BrassInstrument, PitchedPercussion, Instrument
from music21 import Music21Object

from algorithms import *
from config import GLOBALS, MIN_TEMPO


def read_phylo_tree(sequence_file):
    tree = Phylo.read(sequence_file.split('.')[0] + '.dnd', 'newkick')
    Phylo.draw_ascii(tree)


# returns array of possible motifs
def gen_motifs(fasta_file, **args):
    cmd = []
    cmd.append('meme')
    cmd.append(fasta_file)
    cmd.append('-dna')
    cmd.append('-mod')
    cmd.append('zoops')

    valid_args = ['nmotifs',  # max number of motifs
                  'nsites',  # number of sites for each motif
                  'prior',  # prior distribution file
                  'minw',  # minimum motif width
                  'maxw']  # maximum motif width

    output = 'meme_out'
    for key, value in args.iteritems():
        if key not in valid_args:
            raise Exception('Invalid argument: ', key)

        if key == 'o' or key == 'oc':
            output = value

        cmd.append("-" + key)
        cmd.append(str(value))

    with open(fasta_file, 'rU') as handle:

        subprocess.call(cmd)

        with open(output + '/meme.txt', 'rU') as meme_file:
            record = motifs.parse(meme_file, 'meme')
            return record


# aux function
# creates a generator from an iterable (for example, another generator)
# from the original iterable's first n elements
def generator_from_iterable(iterable, n):

    i = 0
    for r in iterable:
        if i < n:
            yield r
        else: break
        i += 1


# generates a MSA from a file with a set of sequences
# arguments can be:
#   seq_vector: vector specifying subset of sequences by reference
#   n_sequences: first n sequences of file
#   MSA algorithm (default: Clustal)
def gen_alignment(input_file, seq_vector=None, n_sequences=None, algorithm='mafft', output_file='output'):

    assert input_file is not None and os.path.isfile(input_file)
    assert output_file is not None

    assert seq_vector is not None or n_sequences is not None, \
        'Both arguments are None (sequence vector and number of sequences)'

    assert isinstance(seq_vector, list) or isinstance(n_sequences, int), \
        'Either one of two must be provided: sequence vector or number of sequences'

    assert algorithm in GLOBALS['SUPPORTED ALGORITHMS'], \
        'Algorithm does not match any of the currently supported MSA algorithms'

    assert isinstance(input_file, str)

    iterable = SeqIO.parse(open(input_file, 'rU'), 'fasta')

    tmp_file = 'pre_alignment.fna'

    if seq_vector is not None:
        sequences = (r for r in iterable if r.description.split('|')[-1] in seq_vector)
    else:
        sequences = generator_from_iterable(iterable, n_sequences)

    sequences = [x for x in sequences]
    if len(sequences) == 0:
        print 'No sequences were found'
        sys.exit(0)

    #print sequences
    SeqIO.write(sequences, tmp_file, 'fasta')

    try:

        t0 = time.time()
        if algorithm == 'clustal':

            if not output_file.endswith('.aln'):
                output_file += '.aln'

            algorithm = 'clustalw2'
            cline = ClustalwCommandline(algorithm,
                                        infile=tmp_file,
                                        outfile=output_file + '.aln')
        elif algorithm == 'muscle':

            if not output_file.endswith('.fna'):
                output_file += '.fna'

            alg = r"/usr/local/bin/muscle3.8.31_i86linux64"
            cline = MuscleCommandline(alg, input=tmp_file,
                                      out='source_sequences/muscle_' + str(n_sequences) + '.fna',
                                      clwstrict=True)
        elif algorithm == 'mafft':

            if not output_file.endswith('.fasta'):
                output_file += '.fasta'

            alg = r"/usr/local/bin/mafft"
            cline = MafftCommandline(alg,
                                     input=tmp_file,
                                     clustalout=True)
        else:
            print 'Unknown algorithm\n'
            sys.exit(0)

        stdout, stderr = cline()

        if algorithm == 'mafft':
            with open(output_file, "wb") as handle:
                handle.write(stdout)

        print 'Elapsed time: ' + str((time.time() - t0) / 60)

        return output_file
    except:
        print 'Error aligning with ' + algorithm
        

# retrieves a distance matrix from:
#   a) a multiple sequence alignment
#   b) a file containing a multiple sequence alignment
def get_distance_matrix(msa):

    calculator = DistanceCalculator('identity')
    distance_matrix = calculator.get_distance(msa)

    return np.array([row for row in distance_matrix])


# clusters all sequences in a MSA
def get_clusters_from_alignment(msa, **kwargs):
    
    assert isinstance(msa, MultipleSeqAlignment)

    print 'Retrieving distance matrix'
    dm = get_distance_matrix(msa)

    instruments = np.array(len(msa))

    if dm is not None:
        
        assert 'algorithm' in kwargs.keys(), 'No algorithm specified for clustering'
        
        algorithm = kwargs['algorithm']

        if 'nclusters' not in kwargs.keys():
            nclusters = len(msa) / 2
        else:
            nclusters = kwargs['nclusters']
            assert isinstance(nclusters, int)

        if algorithm == 'kmeans':
                
            from sklearn.cluster import KMeans
            
            model = KMeans(n_clusters=nclusters, random_state=0)
            model.fit(dm)

            clusters = model.labels_
            # centroids = model.cluster_centers_

        elif algorithm == 'hierarchical':

            from scipy.cluster.hierarchy import dendrogram, linkage
            from scipy.cluster.hierarchy import fcluster

            print 'Retrieving cluster tree'
    
            Z = linkage(dm)

            """if 'dendrogram' in kwargs.keys():
                if kwargs['dendrogram']:
    
                    plt.title('Hierarchical Clustering Dendrogram')
                    plt.xlabel('sample index')
                    plt.ylabel('distance')
        
                    dendrogram(
                        Z,
                        leaf_rotation=90.,  # rotates the x axis labels
                        leaf_font_size=8.,  # font size for the x axis labels
                    )
                    plt.savefig('dendogram.png')
            """

            max_d = 0.01 # TODO: make this dynamic
            clusters = fcluster(Z, max_d, criterion='distance')

        else:
            print 'Invalid cluster algorithm'
            raise NotImplementedError

        from random import shuffle

        instruments_pool = PitchedPercussion.__subclasses__()
        shuffle(instruments_pool)
        instruments_pool = instruments_pool[:nclusters]

        # TODO: TEST!
        i = 0
        for cluster in clusters:
            instruments[i] = instruments_pool[cluster]
            i += 1

        return instruments

    return None


# clusters all sequences in a MSA file
def cluster_alignment(alignment, depth=1):

    assert isinstance(alignment, MultipleSeqAlignment)

    print 'Retrieving clusters...'

    clusters = get_clusters_from_alignment(alignment, depth)

    n_clusters = max(clusters)
    if n_clusters <= 4:

        # numpy array containing pointers to each instrument family
        # and the respectively assigned instrument
        sequence_instruments = np.zeros(len(clusters), dtype=('uint8,uint8'))

        import random

        for i in range(0, len(clusters)):

            idx = clusters[i]
            family = GLOBALS['FAMILIES'][idx]
            print family

            try:
                instruments = family.__subclasses__()
            except TypeError:
                instruments = family.__subclasses__(family)

            rnd = random.randint(0, len(instruments) - 1)
            print instruments[rnd]  # TODO: build list of instruments by priorities

            sequence_instruments[i] = (idx, rnd)

    return get_clusters_from_alignment(alignment, depth)


# aux function
# converts a MSA file in any format to 'phylip-relaxed'
def msa_to_phylip(msa):
    assert os.path.isfile(msa), "MSA file does not exist: " + msa

    out_file = msa.split('.')[0] + '.phy'
    AlignIO.convert(msa, 'clustal', out_file, 'phylip-relaxed')

    return out_file


def gen_dynamics_vector(msa, dynamics_algorithm):

    # criteria: local, avg ou median entropy
    assert isinstance(dynamics_algorithm, DynamicsAlgorithm)
    assert 'window_size' in dynamics_algorithm.keys(), 'Empty window for dynamics algorithm'
    assert dynamics_algorithm['algorithm'] == DynamicsAlgorithm.SHANNON_INDEX # todo: only one option for now; implement simpson index afterwards

    window = dynamics_algorithm['window_size']

    if 'gap_threshold' not in dynamics_algorithm.keys():
        gap_threshold = 0.7
    else:
        gap_threshold = dynamics_algorithm['gap_threshold']

    if 'criteria' not in dynamics_algorithm.keys():
        criteria = 'local'
    else:
        criteria = dynamics_algorithm['criteria']

    if 'levels' not in dynamics_algorithm.keys():
        levels = 5
    else:
        levels = dynamics_algorithm['levels']

    aln_len = len(msa[0])

    from math import ceil

    n_windows = ceil(float(aln_len)/window)+1
    gaps_below_thresh = np.zeros(n_windows, dtype=np.bool)

    window_idx = 0

    # first iterating through MSA to identify
    # which windows have a percentage of gaps
    # below the established threshold

    for i in range(0, aln_len, window):

        if i + window > aln_len: window = aln_len - i

        local_is_below_threshold = np.zeros((window,), dtype=np.bool)
        for j in range(i, i+window):

            column = np.array([c for c in msa[:,j]])

            n_gaps = np.count_nonzero(column == '-')

            if float(n_gaps) / len(column) < gap_threshold:
                local_is_below_threshold[j-i] = True

        n_ungapped_regions = len(np.where(local_is_below_threshold)[0])

        if n_ungapped_regions < gap_threshold * window:
            gaps_below_thresh[window_idx] = True

        window_idx += 1

    from scipy.stats import entropy

    # dynamics_vector = np.zeros((n_windows,),
    dynamics_vector = np.zeros((n_windows,),
                               dtype=[('entropy', np.float), ('vol', np.float)])

    entropies_idx = 0

    for i in range(0, aln_len, window):

        if i + window > aln_len: window = aln_len - i

        # if this window has a percentage of gaps
        # above the considered threshold
        if not gaps_below_thresh[entropies_idx]:
            dynamics_vector['entropy'][entropies_idx] = -1
            continue

        local_entropy = np.zeros((window,))

        for j in range(i, i+window):

            column = msa[:, j]

            column_symbols = column[np.where(column != '-')]

            if len(column_symbols) < (1-gap_threshold) * len(column):

                # apply thresholding +
                pass
            else:
                # Shannon entropy of all column symbols

                counts = itemfreq(column_symbols)
                counts = np.array([float(count) for count in counts[:,1]])

                counts /= np.sum(counts)

                local_entropy[j-i] = entropy(counts, base=2)

        if criteria == 'local':
            dynamics_vector['entropy'][entropies_idx] = np.sum(local_entropy)
        elif criteria == 'average':
            dynamics_vector['entropy'][entropies_idx] = np.average(local_entropy)
        elif criteria == 'median':
            dynamics_vector['entropy'][entropies_idx] = np.median(local_entropy)
        else:
            print 'Unsupported criteria ' + str(criteria) + ' for entropy aggregation'
            sys.exit(1)

        entropies_idx += 1

    max_vol = 0.95
    min_vol = 0.30

    entropies = dynamics_vector['entropy']

    split_info = np.array_split(np.sort(np.unique(entropies)), levels)   # splitting info into classes
    volumes = np.linspace(min_vol, max_vol, num=levels)                # vector with all possible volumes

    for i in range(0, int(n_windows)):

        for j in range(0, len(split_info)):
            if entropies[i] == -1:
                dynamics_vector['vol'][i] = -1
            elif entropies[i] <= split_info[j][-1]:

                dynamics_vector['vol'][i] = volumes[j]
                break

    return dynamics_vector


def add_dynamics_to_score(dynamics_vector, score, window_size, instruments, max_rest_tempo=3):

    # consistency check
    assert isinstance(score, stream.Score) and isinstance(dynamics_vector, np.ndarray)
    assert len(instruments) == len(score.parts)
    assert all(isinstance(i, instrument.Instrument) for i in instruments)

    vol_idx = 0
    score_tempo = score.getElementsByClass(tempo.MetronomeMark)[0]

    # creating filtered score
    # starting with empty parts
    final_score = stream.Score()
    length = np.inf

    for p in range(0, len(score.parts)):

        if len(score.parts[p]) < length:
            length = len(score.parts[p])

        part = stream.Part()
        part.insert(0, score_tempo)
        part.insert(0, instruments[p])

        final_score.append(part)

    # iterating through a music score in chunks of 'window_size' length

    for i in range(0, length, window_size):
        window_size = length - i if i + window_size > length else window_size

        print 'len', length, 'window_size', window_size

        if dynamics_vector[vol_idx] <= 0:
            r = note.Rest()

            for part in final_score.parts:
                part.append(r)
                part[-1].seconds = max_rest_tempo

        else:
            # iterating over parts
            for j in range(0, len(final_score.parts)):

                # scores have same number of parts
                final_part = final_score.parts[j]
                part = score.parts[j]

                for k in range(i, i + window_size):

                    n = part[k]
                    if isinstance(n, note.GeneralNote):  # if Note or Rest

                        final_part.append(n)
                        if isinstance(n, note.Note):  # if Note

                            final_part[-1].volume = dynamics_vector[vol_idx]

        vol_idx += 1

    print 'SECS', final_score[0].seconds

    assert len(final_score.parts) == len(score.parts)
    return final_score


# returns a tuple containing:
#   - a word distance vector per word (A,C,G,T)
#   - a label array with the assigned duration of each nucleotide
def gen_pitch_duration_vectors(sequence, pitch_algorithm, durations_algorithm):

    # kwargs:
    #   - window_duration
    #   - step
    #   - duration_mapping

    assert isinstance(pitch_algorithm, PitchAlgorithm) and isinstance(durations_algorithm, DurationsAlgorithm)
    assert sequence is not None

    # step is the number of columns/characters that are mapped
    length = len(sequence)

    # auxiliary structures
    distance_vectors = dict()  # keys are nucleotides; values are np arrays
    last_occurrence = dict()  # aux dict used for word distances

    step = 1
    window = 1500
    window_duration = 8

    for key in durations_algorithm.keys():
        if key == 'n_nucleotides':
            step = durations_algorithm['n_nucleotides']
            assert isinstance(step, int) and step > 0

        elif key == 'window_size':
            window = durations_algorithm['window_size']
            assert isinstance(window, int) and window > 0

        elif key == 'window_duration':
            window_duration = durations_algorithm['window_duration']
            assert (isinstance(window_duration, float) or isinstance(window_duration, int)) and window > 0

    if 'n_nucleotides' in pitch_algorithm.keys():
        assert step == pitch_algorithm['n_nucleotides']

    d_algorithm = durations_algorithm['algorithm']
    p_algorithm = pitch_algorithm['algorithm']

    assert 'scale' in pitch_algorithm.keys()

    if p_algorithm == PitchAlgorithm.WORD_FREQ:
        scale = p_algorithm['scale']
        pitch_freq_vectors = dict()

        assert len(scale) > 0

    # print [x for x in sequence]

    # splitting by window value
    split_seq_len = int(length / window) if length % window == 0 else int(length / window) + 1
    split_sequence = np.zeros((split_seq_len, window), dtype="S1")

    for i in range(0, split_seq_len):

        subseq = sequence[ i * window : i * window + window]
        split_sequence[i][ : len(subseq)] = subseq
        split_sequence[len(subseq) : ] = ''    

    sequence = split_sequence

    n_nucleotide_split_len = int(window / step) if window % step == 0 else int(window / step) + 1
    split_sequence = np.zeros((split_seq_len, n_nucleotide_split_len), dtype="S" + str(step))

    nucleotides_idx = 0
    for i in range(0, len(sequence)):
        
        subseq = sequence[i]
        split_subseq = split_sequence[i]

        for j in range(0, len(subseq), step):

            for k in range(j, j + step):    
                split_subseq[nucleotides_idx] += subseq[k]

            nucleotides_idx += 1

        nucleotides_idx = 0

    # sequence shape - [ [window] [window] ....]
    # window shape - ['n-nucleotide' 'n-nucleotide' ....]
    sequence = split_sequence   

    # print sequence
    assert len(sequence.shape) == 2 

    offset = 0

    # 1d ndarray containing durations in quarter lengths
    durations = np.empty((sequence.shape[0] * sequence.shape[1],), dtype=np.float)
    
    for i in range(0, len(sequence)):

        # a window with n-nucleotide elements
        subset = sequence[i]
        # grouping frequencies of n-nucleotides  within a block
        counts = dict(itemfreq(subset))

        # This algorithm assigns durations dynamically to nucleotides
        # based on their relative frequency
        if d_algorithm == durations_algorithm.FREQUENCIES_DYNAMIC or p_algorithm == PitchAlgorithm.WORD_FREQ:

            counts_sum = 0
            
            # for j in range(i, boundary):                
            for j in range(0, len(subset)):                
                counts_sum += int(counts[subset[j]])

        total_time = 0.0

        # for j in range(i, boundary, step):
        # for j in range(i, boundary):
        for j in range(0, len(subset)):

            if subset[j] == '': continue

            # local_count = int(counts[subset[j - i]])
            local_count = int(counts[subset[j]])
            freq = float(local_count) / len(subset)

            # pitch algorithm
            if p_algorithm == PitchAlgorithm.WORD_DISTANCES or d_algorithm == DurationsAlgorithm.WORD_DISTANCES:

                # TODO: fazer uma primeira passagem pela sequencia inteira
                # para saber o numero exato de nucleotidos e reservar np.arrays??
                letter = subset[j]

                if letter not in distance_vectors.keys():
                    distance_vectors[letter] = []

                else:
                    # diff = j - last_occurrence[letter]
                    diff = j + offset - last_occurrence[letter]
                    distance_vectors[letter].append(diff)

                # last_occurrence[letter] = j
                last_occurrence[letter] = j + offset

            
            if p_algorithm == PitchAlgorithm.WORD_FREQ:

                # e.g. major scale - C-D-E-F-G-A-B-C
                # obtain scale from p_algorithm
                # assign fraction to each note of scale
                # assign fraction of a note to a frequency

                len_scale = len(scale)
                frac = 1.0 / len(scale)

                for k in range(0, len_scale):
                    val = frac * k
                    if freq > val:
                        continue
                    else:

                        if letter not in pitch_freq_vectors.keys():
                            pitch_freq_vectors[letter] = []

                        pitch_freq_vectors[letter].append(val)

            # durations algorithm
            # frequency-biased algorithms
            if d_algorithm == DurationsAlgorithm.FREQUENCIES_DYNAMIC:

                assert counts_sum is not None and counts_sum > 0, 'Inconsistent values for counts of characters in region'

                local_duration = float(window_duration) * float(local_count) / float(counts_sum)
                total_time += local_duration

                # assert local_duration > MIN_TEMPO, \
                #    'Higher tempo required for each subsequence; too short duration was calculated: ' + str(local_duration)

                # todo: test
                if local_duration < MIN_TEMPO:
                    # print 'WARNING: Converting local duration to minimum tempo!'
                    local_duration = MIN_TEMPO

            # duration biased with discrete attributions
            elif d_algorithm == DurationsAlgorithm.FREQUENCIES_DISCRETE:

                duration_labels = np.array(['32nd','16th','eighth','quarter','half','whole'])
                frequencies = np.linspace(0.0, 0.5, num=len(duration_labels)-1)

                # dictionary mapping a discrete value for word frequencies to each duration label
                duration_labels = { frequencies[k] : duration_labels[k] for k in range(0, len(duration_labels)-1) }
                duration_labels['whole'] = 1.0

                local_duration = '32nd'
                keys = duration_labels.keys()

                # finding correspondent label
                for k in keys:
                    if k > freq:
                        local_duration = duration_labels[k]
                        break

                # obtaining duration in quarter lengths
                local_duration = duration.Duration(local_duration).quarterLength
                total_time += local_duration

            elif d_algorithm == DurationsAlgorithm.WORD_DISTANCES:

                duration_labels = np.array(['64th', '32nd','16th','eighth','quarter','half','whole'])

                if len(distance_vectors[letter]) > 0:
                    duration_label = duration_labels[ distance_vectors[letter][-1] % len(duration_labels) ]
                else:
                    duration_label = 'eighth'

                local_duration = duration.Duration(duration_label).quarterLength
                total_time += local_duration

            else:
                print 'Invalid mapping introduced: ', d_algorithm['algorithm']
                raise NotImplementedError

            # durations[j] = local_duration
            durations[j + offset] = local_duration

        if d_algorithm == DurationsAlgorithm.FREQUENCIES_DISCRETE or d_algorithm == DurationsAlgorithm.WORD_DISTANCES:

            if round(float(total_time), 5) != round(float(window_duration), 5):

                ratio = float(window_duration) / float(total_time)
                total_time = 0.0
                # for j in range(i, boundary):
                for j in range(0, len(subset)):
                    durations[j + offset] *= ratio

                    assert durations[j + offset] >= MIN_TEMPO,\
                        'Higher tempo required for each subsequence; too short duration was calculated: ' + str(durations[j + offset])

                    total_time += durations[j + offset]


        offset += len(subset)

    if p_algorithm == PitchAlgorithm.WORD_DISTANCES:

        for x  in distance_vectors.keys(): # iter(distance_vectors.items()):

            diff = offset + 1 - last_occurrence[x]
            distance_vectors[x].append(diff)

        d_vectors_len = 0

        for x in distance_vectors.keys():

            distance_vectors[x] = np.array(distance_vectors[x])
            d_vectors_len += len(distance_vectors[x])

        # assert d_vectors_len * step == length, "Lengths don't match: sequence length = " + str(length) + "; d_vectors length: " + str(d_vectors_len)
    else:

        return pitch_freq_vectors, durations 

    # (distances, frequencies per N words)
    # print distance_vectors  #, frequencies
    return distance_vectors, durations


def gen_stream(score, sequence, pitch_algorithm, durations_algorithm):

    assert isinstance(pitch_algorithm, PitchAlgorithm) and isinstance(durations_algorithm, DurationsAlgorithm)

    if 'window_size' in durations_algorithm.keys():
        assert len(sequence) > durations_algorithm['window_size'], \
            'Invalid piece and window size ' + str(len(sequence)) + ' ' + str(durations_algorithm['window_size'])

    dv, durations = gen_pitch_duration_vectors(sequence, pitch_algorithm, durations_algorithm)


    for x in dv.keys():
        dv[x] = iter(dv[x])

    durations = iter(durations)

    # TODO: integrar esta parte no algoritmo anterior para poupar iteracoes
    # scale_len = len(scale.MajorScale().getPitches())

    assert 'scale' in pitch_algorithm.keys()
    s = pitch_algorithm['scale']
    scale_len = len(s)

    assert isinstance(s, list) and len(s) > 1

    # TODO: continuar
    part = stream.Part()

    # assert isinstance(score_tempo, tempo.MetronomeMark) and score_tempo == score.getElementsByClass(tempo.MetronomeMark)[0]
    # part.insert(0, assigned_instrument)

    print 'Assigning notes and durations from numeric vectors...'

    # for l in sequence:
    step = pitch_algorithm['n_nucleotides']
    window = durations_algorithm['window_size']

    # TODO: make method
    # splitting by window value
    length = len(sequence)
    split_seq_len = int(length / window) if length % window == 0 else int(length / window) + 1
    split_sequence = np.zeros((split_seq_len, window), dtype="S1")

    for i in range(0, split_seq_len):

        subseq = sequence[ i * window : i * window + window]
        split_sequence[i][ : len(subseq)] = subseq
        split_sequence[len(subseq) : ] = ''    

    sequence = split_sequence

    # splitting in n-nucleotides
    n_nucleotide_split_len = window / step if window % step == 0 else window / step + 1
    split_sequence = np.zeros((split_seq_len, n_nucleotide_split_len), dtype="S" + str(step))

    nucleotides_idx = 0
    for i in range(0, len(sequence)):
        
        subseq = sequence[i]
        split_subseq = split_sequence[i]

        for j in range(0, len(subseq), step):

            for k in range(j, j + step):    
                split_subseq[nucleotides_idx] += subseq[k]

            nucleotides_idx += 1

        nucleotides_idx = 0

    sequence = split_sequence

    print 'Shapes', sequence.shape[0], sequence.shape[1]

    for i in range(0, len(sequence)):

        subseq = sequence[i]
        
        for symbol in subseq:

            if symbol == '': continue

            pitch = dv[symbol].next()
            d = durations.next()

            if set(symbol) != ['-']:

                if pitch_algorithm['algorithm'] == PitchAlgorithm.WORD_DISTANCES:
                    
                    n = pitch % scale_len
                    # n = s.getPitches()[n]
                    n = s[n]
                    n = note.Note(n)

                else:

                    frac = 1.0 / len(scale)

                    for i in range(0, len_scale):
                        val = i * frac

                        if pitch == val:
                            n = s[i]
                            n = note.Note(n)

                n.duration = duration.Duration(d)

            else:

                n = note.Rest()
                n.duration = duration.Duration(d)

                n.addLyric(symbol)

                assert isinstance(n, Music21Object)

            part.append(n)

    print 'Inserting part on score', len(part)

    score.insert(0, part)
    print 'Done'


def gen_song(pitch_algorithm, durations_algorithm, dynamics_algorithm, alignment, instruments, piece_length=5000):

    ####### ALIGNMENT HANDLING ##############
    assert (alignment is not None), 'No MSA provided'

    assert alignment \
           and (isinstance(alignment, MultipleSeqAlignment) or
                (isinstance(alignment, str) and os.path.isfile(alignment)))

    if isinstance(alignment, str):

        print 'Reading alignment...'
        aln_file = AlignIO.read(open(alignment, 'rU'), 'clustal')
        aln_file = msa_to_phylip(aln_file)

        print 'Opening phylip file...'
        alignment = AlignIO.read(open(aln_file.split('.')[0] + ".phy"), 'phylip-relaxed')

    assert isinstance(piece_length, int) or isinstance(piece_length, float) and piece_length > 60

    # step = 1 if not pitch_algorithm['n_nucleotides'] else pitch_algorithm['n_nucleotides']

    # piece_length for now is only referring to number of musical elements
    # n_pieces = len(alignment[0]) / (step * piece_length)
    scores = []

    alignment = np.array([[y for y in x] for x in alignment])

    similarities_df = pd.DataFrame(np.empty(np.floor(float(alignment.shape[1]) / 5000).astype(int),
                                            dtype=[('idx', np.uint8), ('jaccard', np.float), ('tempo', np.float)]))

    k = np.random.choice(np.arange(4, 9), 1)[0]
    n_classes = 3

    print 'K =', k

    piece_idx = 0

    for p in range(0, alignment.shape[1], piece_length):

        if alignment.shape[1] - p < piece_length:
            piece_length = alignment.shape[1] - p

        score = stream.Score()

        # TODO: Make tempo dynamic
        # score_tempo = tempo.MetronomeMark('Larghissimo', 19)
        score_tempo = tempo.MetronomeMark('adagio', 125)
        score.insert(0, score_tempo)

        print 'Generating pitches and durations...'

        """subalignments = np.empty((2, alignment.shape[0], piece_length), dtype=np.dtype(str))

        print subalignments[0].shape, alignment[:, p-piece_length:p].shape
        subalignments[0] = alignment[:, p-piece_length:p] # prev
        subalignments[1] = alignment[:, p:p + piece_length]   # current

        similarities_df['idx'][piece_idx] = piece_idx
        similarities_df['jaccard'][piece_idx] = calc_jaccard_similarities(subalignment, k=k, inter_alignments=True)['jaccard'][0]
        piece_idx += 1
        # subalignment = alignment[:, p:p+piece_length]
        """

        subsequence = alignment[:, p : p + piece_length]
        
        for i in range(0, alignment.shape[0]):
            gen_stream(score, subsequence[i], pitch_algorithm, durations_algorithm)

        print 'Checking if parts have the same total duration...'

        # aligning part durations (score or midi cannot be produced with unequal duration parts)
        for part in score.parts:

            # obtaining highest duration from all parts
            # and aligning with it
            diff = score.highestTime - part.highestTime

            if diff > 0:

                while round(diff, 5) > 0:

                    # minimum = duration.Duration('2048th')
                    n = note.Rest()

                    if diff >= float(0.5):
                        n.duration = duration.Duration(0.5)
                    else:
                        if diff >= MIN_TEMPO:
                            n.duration = duration.Duration(diff)
                        else:
                            n.duration = duration.Duration(MIN_TEMPO)

                    assert n.duration.quarterLength >= MIN_TEMPO

                    part.append(n)
                    diff = score.highestTime - part.highestTime

        # dynamics_vector = gen_dynamics_vector(msa, dynamics_algorithm)
        dynamics_vector = gen_dynamics_vector(subsequence, dynamics_algorithm)

        volumes = dynamics_vector['vol']
        window_size = dynamics_algorithm['window_size']

        # score = add_dynamics_to_score(volumes, score, window_size, instruments)
        scores.append(score)

    print similarities_df

    classes = np.arange(40, 145, (145 - 40) / n_classes, dtype=np.uint8)
    print classes

    jaccard_indices = np.array_split(similarities_df['jaccard'], n_classes)
    class_size = len(jaccard_indices[0])

    j = 0
    for i in range(0, len(classes)):
        similarities_df['tempo'][j:j + class_size] = classes[i]
        print 'L', len(similarities_df['tempo'][j:j + class_size])
        j += class_size

    similarities_df = similarities_df.sort_values('idx')

    # parte estatistica e output de ficheiros para @FileWriter
    # retornar score, utilizar dynamics_algorithm, adicionar volumes a score e analisar score
    return scores


def gen_random_seqs(n, MAX, filename):

    short_version = []

    with open('source_sequences/mitochondrion.1.1.genomic.fna', 'rU') as handle:
        seq_iterator = SeqIO.parse(handle, 'fasta')

        i = 0
        for record in seq_iterator:
            if i > MAX:
                break
            else:
                short_version.append(record)
            i += 1

    from random import shuffle
    shuffle(short_version)

    SeqIO.write(short_version[:n], filename, 'fasta')

###### SIMILARITIES ############

"""
# splits a given sequence from an MSA with alphabet {'A','G','C','T','-'} into shingles
# this technique is based on the k-shingles approach used in document matching algorithms
def split_into_shingles(sequence, k=2):

    length = len(sequence)
    if k < 1 or k > length:
        print 'Invalid parameter k ', k, ' for sequence length ', length
        return None

    # tokenizer
    n_shingles = length - k + 1  # experimental value !!
    shingles = np.zeros((n_shingles, k), dtype="S2")

    i = 0
    while length - i >= k:
        # if length - i < k:
        #	break

        for j in range(0, k):
            shingles[i][j] = sequence[i + j]

        i += 1

    return shingles


def calc_jaccard_similarities(sets, k=2, inter_alignments=False):

    assert len(set(len(subset) for subset in sets)) == 1
    assert isinstance(sets, np.ndarray)

    # print sets.shape, len(sets[0])
    # print len(sets[0]) - k + 1
    # print len(sets)

    assert isinstance(inter_alignments, bool)

    minhashes = []

    if inter_alignments:

        assert len(sets.shape) == 3

        shingles = np.empty((sets.shape[0], sets.shape[1] * (sets.shape[2] - k + 1), k), dtype="S2")

        shingle_idx = 0
        set_row_len = sets.shape[2] - k + 1

        for i in range(0, sets.shape[0]):

            m = dk.MinHash()
            for j in range(0, sets.shape[1]):

                # print 'N shingles', len(sets[i][j]) - k + 1

                shingles[i, shingle_idx : shingle_idx + set_row_len] = split_into_shingles(sets[i][j], k=k)
                shingle_idx += set_row_len

            shingle_idx = 0

            shingle_str = [''.join(s) for s in shingles[i].astype(str)]
            for s in shingle_str:
                m.update(s.encode('utf-8'))

            minhashes.append(m)

    # if not inter_alignments:
    else:
        shingles = np.zeros((len(sets), len(sets[0]) - k + 1, k), dtype="S2")

        for i in range(0, len(sets)):

            shingles[i] = split_into_shingles(sets[i], k=k)
            m = dk.MinHash()

            # for s in shingles[i]:
            shingle_str = [''.join(s) for s in shingles[i].astype(str)]
            for s in shingle_str:
                m.update(s.encode('utf-8'))
            minhashes.append(m)

    assert len(sets) == len(minhashes)

    if not inter_alignments:
        n_rows = len(sets) * (len(sets) -1)
    else:

        n_rows = sets.shape[0] - 1

    # df = pd.DataFrame(data=np.zeros(permutations, 3), index='index', columns=['seq i', 'seq j', 'jaccard'], dtype=np.float)
    # jaccard_dict = {'jaccard' : np.zeros(permutations, dtype=np.float), 'seq i': np.zeros(permutations, dtype=np.int), 'seq j' : np.zeros(permutations, dtype=np.int)}

    jaccard_df = pd.DataFrame(np.empty((n_rows, ), dtype=[('i', np.uint8), ('j', np.uint8), ('jaccard', np.float)]))

    row = 0
    for i in range(0, len(sets)):
        for j in range(0, len(sets)):

            if i != j and not ((jaccard_df['i'] == 2) & (jaccard_df['j'] == 5)).any():  # excluding intersections

                str1 = [''.join(s) for s in shingles[i].astype(str)]
                str2 = [''.join(s) for s in shingles[j].astype(str)]

                jaccard = minhashes[i].jaccard(minhashes[j])

                # print i, j, float(len(set(str2) & set(str1))) / len(set(str2) | set(str1))

                jaccard_df['i'][row] = i
                jaccard_df['j'][row] = j
                jaccard_df['jaccard'][row] = jaccard

                row += 1

    # df = pd.DataFrame(data=jaccard_dict)
    return jaccard_df
"""

# score tokenizer
def tokenize_score(score):
    assert isinstance(score, stream.Stream)  # && len(score.parts) <= 1

    assert score.getElementsByClass(tempo.MetronomeMark)

    duration_notes_tokens = np.empty((len(score.getElementsByClass(note.GeneralNote)), 2), dtype="S14")  # dtype=np.dtype()
    # note_tokens = np.empty(len(score.getElementsByClass(note.GeneralNote)), dtype="S2")

    i = 0
    for element in score:

        if isinstance(element, note.GeneralNote):
            d = element.seconds
            n = element.name

            duration_notes_tokens[i][0] = str(d)
            duration_notes_tokens[i][1] = str(n)

            # print duration_tokens[i], note_tokens[i]

            i += 1

    return duration_notes_tokens


"""def get_sequence_similarities(alignment, score, k=2, n=1):

    assert (isinstance(alignment, np.ndarray) or isinstance(alignment, MultipleSeqAlignment)) and isinstance(score, stream.Score)
    assert len(score.parts) > 0

    n_notes = len(score.parts[0].getElementsByClass(note.GeneralNote))

    assert len(alignment) == len(score) and len(alignment[0]) == float(n_notes)/n

    tokenized_score = np.empty((len(score), 2, n_notes), dtype="S14")

    for i in range(0, len(score.parts)):
        tokenized_score[i] = tokenized_score(score.parts[i])

    calc_jaccard_similarities(alignment, k=k)
    calc_jaccard_similarities(tokenized_score[:, 0], k=k)
    calc_jaccard_similarities(tokenized_score[:, 1], k=k)
"""


def cluster_by_lsh(sets, k=2, num_perm=128):

    # list of 2d ndarrays or 3d ndarray
    assert (isinstance(sets, np.ndarray) and len(sets.shape) == 3) or (isinstance(sets, list) and all(isinstance(x, np.ndarray) and len(x.shape) == 2 for x in sets))                                      # 3d ndarray
    assert isinstance(k, int) and k > 0

    n_pieces = len(sets)
    n_rows = sets.shape[1]
    n_cols = sets.shape[2]

    n_sequence = n_cols + k - 1
    n_shingle_elements = n_sequence - k + 1

    # shingles = np.empty((n_pieces, n_rows * (n_shingle_elements)), dtype="S" + str(k))

    minhashes = []

    # pieces
    shingles_idx = 0
    for p in range(0, n_pieces):

        piece = sets[p]

        minhash = dk.MinHash(num_perm=num_perm)
        shingles = np.empty(n_rows * n_shingle_elements, dtype="S" + str(k))

        # iterating sequences from a region
        for s in range(0, len(piece)):

            # input sequence considering surplus characters
            sequence = np.empty((n_sequence,), dtype="S1")
            sequence[0: n_cols] = piece[s]

            if p != n_pieces - 1: # if we aren't on the last piece:

                next_piece = sets[p+1]
                sequence[n_cols :] = next_piece[s][0 : k-1]  # surplus
            else:

                sequence[n_cols :] = 'Z' # TODO: possivelmente substituir por valor mais provavel

            shingled_sequence = split_into_shingles(sequence, k=k)
            assert len(shingled_sequence) == n_shingle_elements, \
                'Shingled sequence: ' + str(len(shingled_sequence)) + ' and fixed len ' + str(n_shingle_elements)

            # print 'Seq len', len(sequence)
            # print 'Len', len(shingled_sequence), 'Seq', shingled_sequence
            # print 'Shingle len', len(shingles[p][shingles_idx : shingles_idx + n_cols + 1])
            # shingles[p][:, shingles_idx: shingles_idx + len(sequence) - 1] = shingled_sequence
            print shingles_idx + n_cols

            # shingles[p][shingles_idx : shingles_idx + n_shingle_elements] = shingled_sequence
            shingles[shingles_idx: shingles_idx + n_shingle_elements] = shingled_sequence
            shingles_idx += n_shingle_elements

        for word in shingles:
            minhash.update(word)

        minhashes.append(minhash)
        shingles_idx = 0

        # shingle_str = [''.join(s) for s in shingles[piece].astype(str)]
        #for s in shingles[piece]:
        #    minhash.update(s.encode('utf-8'))

    assert len(minhashes) == n_pieces
    print shingles

    distance_matrix = np.empty((n_pieces, n_pieces), dtype=np.float)

    for i in range(0, len(minhashes)):
        for j in range(0, len(minhashes)):

            if i == j:
                distance_matrix[i][j] = 0
            else:

                similarity = minhashes[i].jaccard(minhashes[j])

                if similarity == 0:
                    distance_matrix[i][j] = 1
                else:
                    distance_matrix[i][j] = 1 / similarity

    print distance_matrix

    from scipy.cluster.hierarchy import dendrogram
    from scipy.cluster.hierarchy import fcluster, linkage

    Z = linkage(distance_matrix)

    import matplotlib.pyplot as plt
    dendrogram(Z, show_leaf_counts=True)

    plt.show()

    return fcluster(Z, 0.3)


# splits a given sequence from an MSA with alphabet {'A','G','C','T','-'} into shingles
# this technique is based on the k-shingles approach used in document matching algorithms
def split_into_shingles(sequence, k=2):

    length = len(sequence)
    if k < 1 or k > length:
        print 'Invalid parameter k ', k, ' for sequence length ', length
        return None

    # tokenizer
    n_shingles = length - k + 1  # experimental value !!

    shingles = np.zeros((n_shingles, ), dtype="S" + str(k))

    i = 0
    while length - i >= k:

        for s in sequence[i : i + k]:
            shingles[i] += s
        # shingles[i] = [''.join(s) for s in sequence[i : i + k].astype(str)]
        i += 1

    print shingles
    return shingles



if __name__ == "__main__":

    msa = AlignIO.read('output.fasta', 'clustal')
    msa = np.array([[y for y in x] for x in msa])


    """piece_length = 5000

    pieces = []

    pitch_algorithm = PitchAlgorithm(PitchAlgorithm.WORD_DISTANCES, scale_vector=scale.MajorScale(), n_nucleotides=1)
    durations_algorithm = DurationsAlgorithm(DurationsAlgorithm.FREQUENCIES_DYNAMIC, window_size=1000, window_duration=500,
                                        n_nucleotides=1)

    print np.ceil(float(msa.shape[1])/5000)

    similarities_df = pd.DataFrame(np.empty(np.floor(float(msa.shape[1]) / 5000).astype(int), dtype=[('idx', np.uint8), ('jaccard', np.float), ('tempo', np.float)]))
    j_idx = 0

    k = np.random.choice(np.arange(4, 9), 1)[0]
    n_classes = 3

    print 'K =', k

    for p in range(5000, len(msa[0]), 5000):

        piece_length = 5000 if msa.shape[1] - p >= 5000 else msa.shape[1] - p

        subalignment = np.empty((2, msa.shape[0], piece_length), dtype=np.dtype(str))

        subalignment[0] = msa[:, p-piece_length:p]
        subalignment[1] = msa[:, p:p + piece_length]

        print j_idx
        similarities_df['idx'][j_idx] = j_idx
        similarities_df['jaccard'][j_idx] = calc_jaccard_similarities(subalignment, k=k, inter_alignments=True)['jaccard'][0]
        j_idx += 1

        score = stream.Score()

        score_tempo = tempo.MetronomeMark('adagio', 125)
        score.insert(0, score_tempo)

        pieces.append(score)


    print similarities_df
    j_idx = 0

    classes = np.arange(40, 145, (145 - 40) / n_classes, dtype=np.uint8)
    print classes

    similarities_df = similarities_df.sort_values('jaccard')
    jaccard_indices = np.array_split(similarities_df['jaccard'], n_classes)

    class_size = len(jaccard_indices[0])
    print

    j = 0
    for i in range(0, len(classes)):
        similarities_df['tempo'][j:j + class_size] = classes[i]
        print 'L', len(similarities_df['tempo'][j:j + class_size])
        j += class_size

    print similarities_df.sort_values('idx')
    # jaccard_indices['tempo'] = pd.Series(data=np.zeros(len(jaccard_indices['i'])))"""