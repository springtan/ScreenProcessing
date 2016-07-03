# pipeline to generate read counts and phenotype scores directly from gzipped sequencing data

import os
import sys
import gzip
import multiprocessing
import fnmatch
import glob
import csv
import argparse
from Bio import SeqIO

### Sequence File to Trimmed Fasta Functions ###

def parallelSeqFileToCountsParallel(fastqGzFileNameList, fastaFileNameList, countFileNameList, processPool, libraryFasta, startIndex=None, stopIndex=None, test=False):

	if len(fastqGzFileNameList) != len(fastaFileNameList):
		raise ValueError('In and out file lists must be the same length')

	arglist = zip(fastqGzFileNameList, fastaFileNameList, countFileNameList, [libraryFasta]*len(fastaFileNameList), 
                  [startIndex]*len(fastaFileNameList),[stopIndex]*len(fastaFileNameList), [test]*len(fastaFileNameList)) #[seqToIdDict]*len(fastaFileNameList), [idsToReadcountDict.copy() for i in range(len(fastaFileNameList))]
# 	print len(arglist), len(arglist[0]), len(fastqGzFileNameList)
	
	readsPerFile = processPool.map(seqFileToCountsWrapper, arglist)

	return zip(fastaFileNameList,readsPerFile)


def seqFileToCountsWrapper(arg):
	
	trimmingFuction = None

	for fileTup in acceptedFileTypes:
		if fnmatch.fnmatch(arg[0],fileTup[0]):
			trimmingFuction = fileTup[1]

	if trimmingFuction == None:
		raise ValueError('Sequencing file type not recognized!')

	return trimmingFuction(*arg)

def fastqGzToTrimmedFasta(fastqGzFileName, fastaFileName, countFileName, libraryFasta, startIndex=None, stopIndex=None, test=False):
	printNow('Processing %s' % fastqGzFileName)
	with gzip.open(fastqGzFileName) as filehandle:
		numReads = fastqToCounts(filehandle,fastaFileName,countFileName, libraryFasta, startIndex,stopIndex,test)

	return numReads

def fastqToTrimmedFasta(fastqFileName, fastaFileName, countFileName, libraryFasta, startIndex=None, stopIndex=None, test=False):
	printNow('Processing %s' % fastqFileName)
	with open(fastqFileName) as filehandle:
		numReads = fastqToCounts(filehandle,fastaFileName,countFileName, libraryFasta,startIndex,stopIndex,test)

	return numReads

def fastaToTrimmedFasta(inFastaName, outFastaName, countFileName, libraryFasta, startIndex=None, stopIndex=None, test=False):
	printNow('Processing %s' % inFastaName)
	with open(inFastaName) as filehandle:
		numReads = fastaToCounts(filehandle, outFastaName,countFileName, libraryFasta,startIndex,stopIndex,test)

	return numReads

def fastqToCounts(infile, fastaFileName, countFileName, libraryFasta, startIndex=None, stopIndex=None, test=False):
	seqToIdDict, idsToReadcountDict, expectedReadLength = parseLibraryFasta(libraryFasta)
	
	curRead = 0

	with open(fastaFileName,'w') as unalignedFile:
		for i, fastqLine in enumerate(infile):
			if i % 4 != 1:
				continue

			else:
				seq = fastqLine.strip()[startIndex:stopIndex]
			
				if i == 1 and len(seq) != expectedReadLength:
					raise ValueError('Trimmed read length does not match expected reference read length')
			
				if seq in seqToIdDict:
					for seqId in seqToIdDict[seq]:
						idsToReadcountDict[seqId] += 1
			
				else:
					unalignedFile.write('>%d\n%s\n' % (i, seq))

				curRead += 1
		
				#allow test runs using only the first N reads from the fastq file
				if test and curRead >= testLines:
					break

	with open(countFileName,'w') as countFile:
		for countTup in (sorted(zip(idsToReadcountDict.keys(), idsToReadcountDict.values()))):
			countFile.write('%s\t%d\n' % countTup)

	return curRead


### Map File to Counts File Functions ###

def parseLibraryFasta(libraryFasta):
	seqToIds, idsToReadcounts, readLengths = dict(), dict(), []

	with open(libraryFasta) as infile:
		for seqrecord in SeqIO.parse(infile,'fasta'):
			seq = str(seqrecord.seq)
			id = seqrecord.id

			if seq not in seqToIds:
				seqToIds[seq] = []
			seqToIds[seq].append(id)

			idsToReadcounts[id] = 0

			readLengths.append(len(seq))

	if max(readLengths) != min(readLengths):
		print min(readLengths), max(readLengths)
		raise ValueError('Library reference sequences are of inconsistent lengths')

	return seqToIds, idsToReadcounts, readLengths[0]


### Utility Functions ###
def parseSeqFileNames(fileNameList):
	infileList = []
	outfileBaseList = []

	for inputFileName in fileNameList:					#iterate through entered filenames for sequence files
		for filename in glob.glob(inputFileName): 		#generate all possible files given wildcards
			for fileType in zip(*acceptedFileTypes)[0]:	#iterate through allowed filetypes
				if fnmatch.fnmatch(filename,fileType):
					infileList.append(filename)
					outfileBaseList.append(os.path.split(filename)[-1].split('.')[0])

	return infileList, outfileBaseList

def makeDirectory(path):
	try:
		os.makedirs(path)
	except OSError:
		#printNow(path + ' already exists')
		pass

def printNow(printInput):
	print printInput
	sys.stdout.flush()

### Global variables ###
acceptedFileTypes = [('*.fastq.gz',fastqGzToTrimmedFasta),
					('*.fastq', fastqToTrimmedFasta),
					('*.fa', fastaToTrimmedFasta),
					('*.fasta', fastaToTrimmedFasta),
					('*.fna', fastaToTrimmedFasta)]


testLines = 10000


if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='Process raw sequencing data from screens to counts files in parallel')
	parser.add_argument('Library_Fasta', help='Fasta file of expected library reads.')
	parser.add_argument('Out_File_Path', help='Directory where output files should be written.')
	parser.add_argument('Seq_File_Names', nargs='+', help='Name(s) of sequencing file(s). Unix wildcards can be used to select multiple files at once. The script will search for all *.fastq.gz, *.fastq, and *.fa(/fasta/fna) files with the given wildcard name.')
			
	parser.add_argument('-u','--Unaligned_Indices', nargs='+', help='Bowtie indices to test unaligned reads for possible cross-contaminations.')
	parser.add_argument('-p','--processors', type=int, default = 1)
	parser.add_argument('--trim_start', type=int)
	parser.add_argument('--trim_end', type=int)
	parser.add_argument('--test', action='store_true', default=False, help='Run the entire script on only the first %d reads of each file. Be sure to delete or move all test files before re-running script as they will not be overwritten.' % testLines)

	args = parser.parse_args()
	#printNow(args)

	numProcessors = max(args.processors, 1)

	infileList, outfileBaseList = parseSeqFileNames(args.Seq_File_Names)

# 	printNow('Loading reference library...')
# 	seqToIds, idsToReadcounts, expectedReadLength = parseLibraryFasta(args.Library_Fasta)
			
	## unzip and trim all files ##
	trimmedFastaPath = os.path.join(args.Out_File_Path,'unaligned_reads')
	makeDirectory(trimmedFastaPath)
	countFilePath = os.path.join(args.Out_File_Path,'count_files')
	makeDirectory(countFilePath)

	fastaFileNameList = [outfileName + '_unaligned.fa' for outfileName in outfileBaseList] 
	fastaFilePathList = [os.path.join(trimmedFastaPath, fastaFileName) for fastaFileName in fastaFileNameList]
	countFilePathList = [os.path.join(countFilePath,outfileName + '_' + os.path.split(args.Library_Fasta)[-1] + '.counts') for outfileName in outfileBaseList]

#    filesToProcess = [filePaths for filePaths in zip(bowtieMapPathList,countPathList) if os.path.split(filePaths[1])[-1] not in os.listdir(countFilePath)]
#	if len(allFilesToProcess) != 0:
#		infilesToProcess, fastasToProcess = zip(*allFilesToProcess)
#	else:
#		infilesToProcess, fastasToProcess = [],[]
#	fastaFilePathsToProcess = [os.path.join(trimmedFastaPath, fastaFileName) for fastaFileName in fastasToProcess]

	
	if len(infileList) != 0:
		printNow('Parsing and trimming sequence files...')
		sys.stdout.flush()

		pool = multiprocessing.Pool(min(len(infileList),numProcessors))

		resultList = parallelSeqFileToCountsParallel(infileList, fastaFilePathList, countFilePathList, pool, args.Library_Fasta, args.trim_start, args.trim_end, args.test)
		for result in resultList:
			print result[0] + ':\t' + repr(result[1]) + ' reads'
		
		pool.close()
		pool.join()

	printNow('Done counting mapped reads')