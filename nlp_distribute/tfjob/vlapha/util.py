# -*- coding: utf-8 -*-

import tensorflow as tf
import numpy as np
import re
from collections import Counter
import string


def read_and_decode(filename_queue,config,random_crop=False, random_clip=False, is_test=True):
    para_limit = config.test_para_limit if is_test else config.para_limit
    ques_limit = config.test_ques_limit if is_test else config.ques_limit
    char_limit = config.char_limit
    alternative_limit = config.alternatives_limit
    reader = tf.TFRecordReader()
    _, serialized_example = reader.read(filename_queue)
    features = tf.parse_single_example(
      serialized_example,
        features={
            "context_idxs": tf.FixedLenFeature([], tf.string),
            "ques_idxs": tf.FixedLenFeature([], tf.string),
            "context_char_idxs": tf.FixedLenFeature([], tf.string),
            "ques_char_idxs": tf.FixedLenFeature([], tf.string),
            "alternatives_tokens": tf.FixedLenFeature([], tf.string),
            "y1": tf.FixedLenFeature([], tf.string),
            "id": tf.FixedLenFeature([], tf.int64)
        }
    )

    context_idxs = tf.reshape(tf.decode_raw(features["context_idxs"], tf.int32), [para_limit])
    ques_idxs = tf.reshape(tf.decode_raw(features["ques_idxs"], tf.int32), [ques_limit])
    alternative_idxs = tf.reshape(tf.decode_raw(features["alternative_idxs"], tf.int32), [3, alternative_limit])
    context_char_idxs = tf.reshape(tf.decode_raw(features["context_char_idxs"], tf.int32), [para_limit, char_limit])
    ques_char_idxs = tf.reshape(tf.decode_raw(features["ques_char_idxs"], tf.int32), [ques_limit, char_limit])
    alternative_char_idxs = tf.reshape(tf.decode_raw(features["alternative_char_idxs"], tf.int32),
                                       [3, alternative_limit, char_limit])
    qa_id = features["id"]

    context_idxs, ques_idxs, alternative_idxs, context_char_idxs, ques_char_idxs, alternative_char_idxs, qa_id= tf.train.batch([context_idxs, ques_idxs, alternative_idxs, context_char_idxs, ques_char_idxs, alternative_char_idxs,qa_id],
                                    batch_size=20,
                                    capacity=8000,
                                    num_threads=4)
    return context_idxs, ques_idxs, alternative_idxs, context_char_idxs, ques_char_idxs, alternative_char_idxs,qa_id
def get_record_parser(config, is_test=False):
    def parse(example):
        para_limit = config.test_para_limit if is_test else config.para_limit
        ques_limit = config.test_ques_limit if is_test else config.ques_limit
        char_limit = config.char_limit
        if is_test!=True:
            features = tf.parse_single_example(example,
                                               features={
                                                   "context_idxs": tf.FixedLenFeature([], tf.string),
                                                   "ques_idxs": tf.FixedLenFeature([], tf.string),
                                                   "context_char_idxs": tf.FixedLenFeature([], tf.string),
                                                   "ques_char_idxs": tf.FixedLenFeature([], tf.string),
                                                   "alternatives_tokens":tf.FixedLenFeature([], tf.string),
                                                   "y1": tf.FixedLenFeature([], tf.string),
                                                   "id": tf.FixedLenFeature([], tf.int64)
                                               })
        else:
            features = tf.parse_single_example(example,
                                               features={
                                                   "context_idxs": tf.FixedLenFeature([], tf.string),
                                                   "ques_idxs": tf.FixedLenFeature([], tf.string),
                                                   "context_char_idxs": tf.FixedLenFeature([], tf.string),
                                                   "ques_char_idxs": tf.FixedLenFeature([], tf.string),
                                                   "alternatives_tokens": tf.FixedLenFeature([], tf.string),
                                               })
        context_idxs = tf.reshape(tf.decode_raw(features["context_idxs"], tf.int32), [para_limit])
        ques_idxs = tf.reshape(tf.decode_raw(features["ques_idxs"], tf.int32), [ques_limit])
        context_char_idxs = tf.reshape(tf.decode_raw(features["context_char_idxs"], tf.int32), [para_limit, char_limit])
        ques_char_idxs = tf.reshape(tf.decode_raw(features["ques_char_idxs"], tf.int32), [ques_limit, char_limit])
        alternatives_tokens=tf.decode_raw(features["ques_char_idxs"], tf.int32)
        if is_test!=True:
            qa_id = features["id"]
            y1 = tf.reshape(tf.decode_raw(features["y1"], tf.float32), [3])
            return context_idxs, ques_idxs, context_char_idxs, ques_char_idxs,y1, qa_id,alternatives_tokens
        else:
            return context_idxs, ques_idxs, context_char_idxs, ques_char_idxs,alternatives_tokens
    return parse

def get_batch_dataset(record_file, parser, config):
    num_threads = tf.constant(config.num_threads, dtype=tf.int32)
    dataset = tf.data.TFRecordDataset(record_file).map(
        parser, num_parallel_calls=num_threads).shuffle(config.capacity).repeat() #利用多线程把训练数据加载
    if config.is_bucket:
        buckets = [tf.constant(num) for num in range(*config.bucket_range)]

        def key_func(context_idxs, ques_idxs, context_char_idxs, ques_char_idxs, y1, y2, qa_id):
            c_len = tf.reduce_sum(
                tf.cast(tf.cast(context_idxs, tf.bool), tf.int32))
            buckets_min = [np.iinfo(np.int32).min] + buckets
            buckets_max = buckets + [np.iinfo(np.int32).max]
            conditions_c = tf.logical_and(
                tf.less(buckets_min, c_len), tf.less_equal(c_len, buckets_max))
            bucket_id = tf.reduce_min(tf.where(conditions_c))
            return bucket_id

        def reduce_func(key, elements):
            return elements.batch(config.batch_size)

        dataset = dataset.apply(tf.contrib.data.group_by_window(
            key_func, reduce_func, window_size=5 * config.batch_size)).shuffle(len(buckets) * 25)
    else:
        dataset = dataset.batch(config.batch_size) #对数据进行batch分批
    return dataset


def get_dataset(record_file, parser, config):
    num_threads = tf.constant(config.num_threads, dtype=tf.int32)
    dataset = tf.data.TFRecordDataset(record_file).map(
        parser, num_parallel_calls=num_threads).repeat().batch(config.batch_size)
    return dataset


def convert_tokens(eval_file, qa_id, pp1, pp2):
    answer_dict = {}
    remapped_dict = {}
    for qid, p1, p2 in zip(qa_id, pp1, pp2):
        context = eval_file[str(qid)]["context"]
        spans = eval_file[str(qid)]["spans"]
        uuid = eval_file[str(qid)]["uuid"]
        start_idx = spans[p1][0]
        end_idx = spans[p2][1]
        answer_dict[str(qid)] = context[start_idx: end_idx]
        remapped_dict[uuid] = context[start_idx: end_idx]
    return answer_dict, remapped_dict


def evaluate(eval_file, answer_dict):
    f1 = exact_match = total = 0
    for key, value in answer_dict.items():
        total += 1
        ground_truths = eval_file[key]["answers"]
        prediction = value
        exact_match += metric_max_over_ground_truths(
            exact_match_score, prediction, ground_truths)
        f1 += metric_max_over_ground_truths(f1_score,
                                            prediction, ground_truths)
    exact_match = 100.0 * exact_match / total
    f1 = 100.0 * f1 / total
    return {'exact_match': exact_match, 'f1': f1}


def normalize_answer(s):

    def remove_articles(text):
        return re.sub(r'\b(a|an|the)\b', ' ', text)

    def white_space_fix(text):
        return ' '.join(text.split())

    def remove_punc(text):
        exclude = set(string.punctuation)
        return ''.join(ch for ch in text if ch not in exclude)

    def lower(text):
        return text.lower()

    return white_space_fix(remove_articles(remove_punc(lower(s))))


def f1_score(prediction, ground_truth):
    prediction_tokens = normalize_answer(prediction).split()
    ground_truth_tokens = normalize_answer(ground_truth).split()
    common = Counter(prediction_tokens) & Counter(ground_truth_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0
    precision = 1.0 * num_same / len(prediction_tokens)
    recall = 1.0 * num_same / len(ground_truth_tokens)
    f1 = (2 * precision * recall) / (precision + recall)
    return f1


def exact_match_score(prediction, ground_truth):
    return (normalize_answer(prediction) == normalize_answer(ground_truth))


def metric_max_over_ground_truths(metric_fn, prediction, ground_truths):
    scores_for_ground_truths = []
    for ground_truth in ground_truths:
        score = metric_fn(prediction, ground_truth)
        scores_for_ground_truths.append(score)
    return max(scores_for_ground_truths)
