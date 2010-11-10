import argparse, math, itertools
import cPickle as pickle
import nltk.corpus
from nltk.classify import DecisionTreeClassifier, MaxentClassifier, NaiveBayesClassifier
from nltk.corpus.reader import TaggedCorpusReader, SwitchboardCorpusReader
from nltk.corpus.util import LazyCorpusLoader
from nltk.tag import ClassifierBasedPOSTagger
from nltk_trainer.tagging.readers import NumberedTaggedSentCorpusReader
from nltk_trainer.tagging.training import train_brill_tagger

########################################
## command options & argument parsing ##
########################################

parser = argparse.ArgumentParser(description='Train a NLTK Classifier')

parser.add_argument('corpus', help='corpus name/path relative to an nltk_data directory')
parser.add_argument('--filename', help='''filename/path for where to store the
	pickled classifier, the default is {corpus}_{algorithm}.pickle in
	~/nltk_data/classifiers''')
parser.add_argument('--no-pickle', action='store_true', default=False,
	help="don't pickle and save the classifier")
parser.add_argument('--trace', default=1, type=int,
	help='How much trace output you want, defaults to 1. 0 is no trace output.')

tagger_group = parser.add_argument_group('Tagger Choices')
tagger_group.add_argument('--classifier', default=None,
	choices=['NaiveBayes', 'DecisionTree', 'Maxent'] + MaxentClassifier.ALGORITHMS,
	help='''ClassifierBasedPOSTagger algorithm to use, default is None.
	Maxent uses the default Maxent training algorithm, either CG or iis.''')
tagger_group.add_argument('--brill', action='store_true', default=False,
	help='Train a Brill Tagger in front of the other tagger')

brill_group = parser.add_argument_group('Brill Tagger Options')
brill_group.add_argument('--template_bounds', type=int, default=1,
	help='''Choose the max bounds for Brill Templates to train a Brill Tagger.
	The default is 0 for no Brill Tagger.''')
brill_group.add_argument('--max_rules', type=int, default=200)
brill_group.add_argument('--min_score', type=int, default=2)

corpus_group = parser.add_argument_group('Training Corpus')
# TODO: more choices
corpus_group.add_argument('--reader', choices=('tagged',),
	default=None,
	help='specify part-of-speech tagged corpus')
corpus_group.add_argument('--fraction', default=1.0, type=float,
	help='Fraction of corpus to use for training')
# TODO: support corpora like conll2000 that have train.txt & test.txt

eval_group = parser.add_argument_group('Tagger Evaluation',
	'Evaluation metrics for part-of-speech taggers')
eval_group.add_argument('--no-eval', action='store_true', default=False,
	help="don't do any evaluation")
# TODO: are there any metrics other than accuracy?

maxent_group = parser.add_argument_group('Maxent Classifier Tagger',
	'These options only apply when a Maxent classifier is chosen.')
maxent_group.add_argument('--max_iter', default=10, type=int,
	help='maximum number of training iterations, defaults to 10')
maxent_group.add_argument('--min_ll', default=0, type=float,
	help='stop classification when average log-likelihood is less than this, default is 0')
maxent_group.add_argument('--min_lldelta', default=0.1, type=float,
	help='stop classification when the change in average log-likelihood is less than this, default is 0.1')

decisiontree_group = parser.add_argument_group('Decision Tree Classifier Tagger',
	'These options only apply when the DecisionTree classifier is chosen')
decisiontree_group.add_argument('--entropy_cutoff', default=0.05, type=float,
	help='default is 0.05')
decisiontree_group.add_argument('--depth_cutoff', default=100, type=int,
	help='default is 100')
decisiontree_group.add_argument('--support_cutoff', default=10, type=int,
	help='default is 10')

args = parser.parse_args()

###################
## corpus reader ##
###################

if not args.reader:
	if args.corpus == 'timit':
		tagged_corpus = LazyCorpusLoader('timit', NumberedTaggedSentCorpusReader, '.+\.tags')
	else:
		tagged_corpus = getattr(nltk.corpus, args.corpus)
	
	if not tagged_corpus:
		raise ValueError('%s is an unknown corpus')
	
	if args.trace:
		print 'loading nltk.corpus.%s' % args.corpus
	# trigger loading so it has its True class
	tagged_corpus.fileids()
	
	if isinstance(tagged_corpus, SwitchboardCorpusReader):
		tagged_sents = list(itertools.chain(*[[list(s) for s in d if s] for d in tagged_corpus.tagged_discourses()]))
	# TODO: support timit corpus
	else:
		tagged_sents = tagged_corpus.tagged_sents()
else:
	# TODO: support generic usage of TaggedCorpusReader, ConllChunkCorpusReader,
	# BracketParseCorpusReader
	reader_class = {
		'tagged': TaggedCorpusReader
		# TODO: also allow CategorizedTaggedCorpusReader, ConllCorpusReader (with column types)
		# SwitchboardCorpusReader, and whatever's needed for timit corpus
	}
	
	# TODO: options for sep, word_tokenizer, sent_tokenizer, para_block_reader,
	# tag_mapping_function
	
	tagged_corpus = LazyCorpusLoader(args.corpus, reader_class[args.reader])

nsents = len(tagged_sents)

if args.fraction == 1.0:
	train_sents = test_sents = tagged_sents
else:
	cutoff = int(math.ceil(nsents * args.fraction))
	train_sents = tagged_sents[:cutoff]
	test_sents = tagged_sents[cutoff:]

if args.trace:
	print '%d tagged sents, training on %d' % (nsents, len(train_sents))

#######################
## classifier tagger ##
#######################

classifier_train_kwargs = {}

if args.classifier == 'DecisionTree':
	classifier_train = DecisionTreeClassifier.train
	classifier_train_kwargs['binary'] = False
	classifier_train_kwargs['entropy_cutoff'] = args.entropy_cutoff
	classifier_train_kwargs['depth_cutoff'] = args.depth_cutoff
	classifier_train_kwargs['support_cutoff'] = args.support_cutoff
	classifier_train_kwargs['verbose'] = args.trace
elif args.classifier == 'NaiveBayes':
	classifier_train = NaiveBayesClassifier.train
elif args.classifier:
	if args.classifier != 'Maxent':
		classifier_train_kwargs['algorithm'] = args.classifier
	
	classifier_train = MaxentClassifier.train
	classifier_train_kwargs['max_iter'] = args.max_iter
	classifier_train_kwargs['min_ll'] = args.min_ll
	classifier_train_kwargs['min_lldelta'] = args.min_lldelta
	classifier_train_kwargs['trace'] = args.trace

if args.classifier:
	if args.trace:
		print 'training a %s ClassifierBasedPOSTagger' % args.classifier
	
	# TODO: options for cutoff_prob
	tagger = ClassifierBasedPOSTagger(train=train_sents, verbose=args.trace,
		classifier_builder=lambda train_feats: classifier_train(train_feats, **classifier_train_kwargs))

# TODO: support other taggers: sequential backoff chaining, brill, TnT, default

###################
## other taggers ##
###################

if args.brill:
	tagger = train_brill_tagger(tagger, train_sents, args.template_bounds,
		trace=args.trace, max_rules=args.max_rules, min_score=args.min_score)

################
## evaluation ##
################

if not args.no_eval:
	print 'evaluating %s' % tagger
	print 'accuracy: %f' % tagger.evaluate(test_sents)