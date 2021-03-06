#!/usr/bin/env python

import settings
from copy import deepcopy
from numpy import exp, dot, zeros, outer, random, dtype, get_include, amax,\
    uint32, seterr, array, uint8, vstack, argsort, fromstring, sqrt, newaxis, ndarray, empty, sum as np_sum

FAST_VERSION = -1
IS_DOUBLE = settings.use_double

if IS_DOUBLE:
    from numpy import float64 as REAL
else:
    from numpy import float32 as REAL

def train_sent_vec(model, sent_vec, sentence, alpha, work=None, neu1=None, sent_vec_grad=None):
    if model.sg:
        return train_sent_vec_sg(model, sent_vec, sentence, alpha, work, neu1, sent_vec_grad)
    else:
        return train_sent_vec_cbow(model, sent_vec, sentence, alpha, work, neu1, sent_vec_grad)

def train_sent_vec_sg(model, sent_vec, sentence, alpha, work=None, neu1=None, sent_vec_grad=None):
    """
    Update skip-gram model by training on a single sentence.

    The sentence is a list of Vocab objects (or None, where the corresponding
    word is not in the vocabulary. Called internally from `Sent2Vec.train()`.

    This is the non-optimized, Python version. If you have cython installed, gensim
    will use the optimized version from word2vec_inner instead.

    """
    w2vmodel = model.w2v
    if model.negative:
        # precompute negative labels
        labels = zeros(model.negative + 1)
        labels[0] = 1.0

    for pos, word in enumerate(sentence):
        if word is None:
            continue  # OOV word in the input sentence => skip
        reduced_window = random.randint(w2vmodel.window)  # `b` in the original word2vec code

        # now go over all words from the (reduced) window, predicting each one in turn
        start = max(0, pos - w2vmodel.window + reduced_window)
        for pos2, word2 in enumerate(sentence[start : pos + w2vmodel.window + 1 - reduced_window], start):
            # don't train on OOV words
            if word2:
                # l1 = w2vmodel.syn0[word.index]
                l1 = sent_vec
                neu1e = zeros(l1.shape)

                if model.hs:
                    # work on the entire tree at once, to push as much work into numpy's C routines as possible (performance)
                    l2a = deepcopy(w2vmodel.syn1[word2.point])  # 2d matrix, codelen x layer1_size
                    fa = 1.0 / (1.0 + exp(-dot(l1, l2a.T)))  #  propagate hidden -> output
                    ga = (1 - word2.code - fa) * alpha  # vector of error gradients multiplied by the learning rate
                    if model.word_learn == 1: w2vmodel.syn1[word2.point] += outer(ga, l1)  # learn hidden -> output
                    neu1e += dot(ga, l2a) # save error

                if model.negative:
                    # use this word (label = 1) + `negative` other random words not from this sentence (label = 0)
                    word_indices = [word2.index]
                    while len(word_indices) < w2vmodel.negative + 1:
                        w = w2vmodel.table[random.randint(w2vmodel.table.shape[0])]
                        if w != word2.index:
                            word_indices.append(w)
                    l2b = w2vmodel.syn1neg[word_indices] # 2d matrix, k+1 x layer1_size
                    fb = 1. / (1. + exp(-dot(l1, l2b.T))) # propagate hidden -> output
                    gb = (labels - fb) * alpha # vector of error gradients multiplied by the learning rate
                    if model.word_learn == 1: w2vmodel.syn1neg[word_indices] += outer(gb, l1) # learn hidden -> output
                    neu1e += dot(gb, l2b) # save error
                sent_vec += neu1e  # learn input -> hidden
    return len([word for word in sentence if word is not None])

    
def train_sent_vec_cbow(model, sent_vec, sentence, alpha, work=None, neu1=None, sent_vec_grad=None):
    """
    Update CBOW model by training on a single sentence.

    The sentence is a list of Vocab objects (or None, where the corresponding
    word is not in the vocabulary. Called internally from `Sent2Vec.train()`.

    This is the non-optimized, Python version. If you have cython installed, gensim
    will use the optimized version from word2vec_inner instead.

    """
    w2vmodel = model.w2v
    if model.negative:
        # precompute negative labels
        labels = zeros(model.negative + 1)
        labels[0] = 1.

    for pos, word in enumerate(sentence):
        if word is None:
            continue  # OOV word in the input sentence => skip
        reduced_window = random.randint(model.window) # `b` in the original word2vec code
        start = max(0, pos - model.window + reduced_window)
        window_pos = enumerate(sentence[start : pos + model.window + 1 - reduced_window], start)
        word2_indices = [word2.index for pos2, word2 in window_pos if (word2 is not None and pos2 != pos)]
        l1 = np_sum(w2vmodel.syn0[word2_indices], axis=0) # 1 x layer1_size
        l1 += sent_vec
        if word2_indices and model.cbow_mean:
            l1 /= (len(word2_indices) + 1) ##modified by jmarui
        neu1e = zeros(l1.shape)

        if model.hs:
            l2a = w2vmodel.syn1[word.point] # 2d matrix, codelen x layer1_size
            fa = 1. / (1. + exp(-dot(l1, l2a.T))) # propagate hidden -> output
            ga = (1. - word.code - fa) * alpha # vector of error gradients multiplied by the learning rate
            if model.word_learn == 1: w2vmodel.syn1[word.point] += outer(ga, l1) # learn hidden -> output
            neu1e += dot(ga, l2a) # save error

        if model.negative:
            # use this word (label = 1) + `negative` other random words not from this sentence (label = 0)
            word_indices = [word.index]
            while len(word_indices) < model.negative + 1:
                w = w2vmodel.table[random.randint(w2vmodel.table.shape[0])]
                if w != word.index:
                    word_indices.append(w)
            l2b = w2vmodel.syn1neg[word_indices] # 2d matrix, k+1 x layer1_size
            fb = 1. / (1. + exp(-dot(l1, l2b.T))) # propagate hidden -> output
            gb = (labels - fb) * alpha # vector of error gradients multiplied by the learning rate
            if model.word_learn == 1: w2vmodel.syn1neg[word_indices] += outer(gb, l1) # learn hidden -> output
            neu1e += dot(gb, l2b) # save error

        if model.word_learn == 1: w2vmodel.syn0[word2_indices] += neu1e # learn input -> hidden, here for all words in the window separately
        sent_vec += neu1e # learn input -> hidden, here for all words in the window separately
    return len([word for word in sentence if word is not None])

def sentvec_sim(model, vec, num, sims):
    vec_len_r = 1.0 / sqrt(dot(vec, vec))
    for i in xrange(sims):
        vec2 = model.sents[i]
        vec2_len_r = 1.0 / sqrt(dot(vec2, vec2))
        sims[i] = dot(model.sents[i], vec) * vec2_len_r
    sims *= vec_len_r

