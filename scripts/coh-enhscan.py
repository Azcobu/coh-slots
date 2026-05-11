'''
1.1 - rewrote file scanner to minimize number of disk reads, improving speed by
      5-6 times.
    - added code to handle pool and inherent powers.
    - fixed IOs so Acc, Acc- and Acc-I are treated the same.
    - better slot detection
1.2 - epic and patron pools, concatenated by name.
    - also sort epics alphabetically, unlike normal powrs which sort by level
'''
import re
from os import listdir, walk
from statistics import median, mean
from itertools import chain
from collections import Counter
import coh_api_parser
import time

banned_powers = ['Gauntlet', 'Offensive Adaptation', 'Efficient Adaptation',
                 'Defensive Adaptation', 'Form of the Mind', 'Form of the Soul',
                 'Form of the Body', 'Adaptation', 'Cryo Ammunition', 
                 'Incendiary Ammunition', 'Chemical Ammunition', 'Swap Ammo']

class CoHPowSlotting:
    """data structure for managing builds"""
    def __init__(self, setname, pwrname, forum, slotting):
        self.setname = setname
        self.pwrname = pwrname
        self.forum = forum
        self.slotting = slotting

    def __repr__(self):
        return f'CPS: {self.slotting}'

def scan_dense_enhs(instr, pwrname):
    """searches a text string for slotting for a specified power"""
    #first find pwr name
    instr = instr[instr.find(': ' + pwrname) + len(pwrname) + 2:]
    # then cut off str at next use of word 'Level' if it's there
    if 'Level' in instr:
        instr = instr[:instr.find('Level')]
    instr = instr[instr.find('-- ') + 3:]
    #now strip out all enh level numbers
    p = re.compile(':\\d+')
    instr = p.sub('', instr)
    if '&lt;' in instr or '&gt;' in instr or instr == '': return []
    ios = sorted([x.strip() for x in instr.split(',') if x.strip() not in \
                   ['Empty', 'Empt', '-', ';">Empty;">', ';">RechRdx;">-I;">']])
    return [x.rpartition('-')[0] if x[-1] == '-' or x[-2:] == '-I' else x for x in ios]

def parse_file(indir, infile, pwrsets):
    """looks through a file for instances of power slotting from a power list"""
    #p = re.compile('[<(].*?[>)]')
    p = re.compile('[<(\\[].*?[\\]>)]')
    slotlist = []
    if 'homecoming' in indir: forum_name = 'hc'
    if 'City of Heroes Forums' in indir: forum_name = 'paragon'
    '''
    with open(indir + '\\' + infile, 'r', encoding='utf-8') as datafile:
        indata = datafile.read()
        if ' Plan by Mids' in indata or 'build was built using Mids' in indata:
        #if ' Plan by Mids' in datafile.read() or 
            datafile.seek(0)
            for line in datafile.readlines(): # this is a problem - reloading from disk rather than memory
                if 'Level' in line:
                    for pwrset in pwrsets:
                        for setname, pwrlist in pwrset.items():
                            powlist = [p.name for p in pwrlist if p.name not in banned_powers]
                            for pwr in powlist:
                                if pwr in line:
                                #QQQQ two types of output here, compact and long-form
                                    if '--' in line: #compact form
                                        #if pwr == 'Hasten' and 'Chandeliere' in line:
                                        #    print('vfdv')
                                        line = p.sub('', line.strip())
                                        if ': ' + pwr in line:
                                            slots = tuple(scan_dense_enhs(line, pwr))
                                            if slots:
                                                new = CoHPowSlotting(setname, pwr, forum_name, slots)
                                                slotlist.append(new)
    '''

    pattern = r'.*Level.*'
    # if re.search(pattern, line):

    with open(indir + '\\' + infile, 'r', encoding='utf-8') as datafile:
        indata = datafile.read()
        if ' Plan by Mids' in indata or 'build was built using Mids' in indata:
            all_lines = indata.splitlines()

            for line in all_lines: # this is a problem - reloading from disk rather than memory
                #if 'Level' in line:
                if re.search(pattern, line):
                    for pwrset in pwrsets:
                        for setname, pwrlist in pwrset.items():
                            powlist = [p.name for p in pwrlist if p.name not in banned_powers]
                            for pwr in powlist:
                                if pwr in line:
                                #QQQQ two types of output here, compact and long-form
                                    if '--' in line: #compact form
                                        #if pwr == 'Hasten' and 'Chandeliere' in line:
                                        #    print('vfdv')
                                        line = p.sub('', line.strip())
                                        if ': ' + pwr in line:
                                            slots = tuple(scan_dense_enhs(line, pwr))
                                            if slots:
                                                new = CoHPowSlotting(setname, pwr, forum_name, slots)
                                                slotlist.append(new)
    return slotlist

def generate_pwr_data(forum, corpus, showfor):
    """display a group of slottings for a particular power/forum combination"""
    show_percent = 25
    outlist = []

    if showfor:
        forum_name = 'Homecoming Forums' if forum == 'hc' else 'Paragon Forums'
        outlist = [f'<details class="indent1"><summary>{forum_name}</summary>']

    if not corpus:
        outlist.append('No data found for this power in forum.')
        if showfor: outlist.append('</details>')
        return ''.join(outlist)

    numfound = len(corpus)
    meanslots = mean([len(x) for x in corpus])
    meanslots = round(meanslots, 2)
    medslots = median([len(x) for x in corpus])
    outlist.append(f'Found {numfound} times. {meanslots} mean slots, ' +\
                   f'{medslots} median slots.<p>')

    # find top show_percent% of results such that 3 <= number <= 10
    showcount = 3
    while sum([x[1] for x in Counter(corpus).most_common(showcount)])\
              < numfound * show_percent/100 and showcount < 10:
        showcount += 1
    #if showcount > 10: showcount = 10

    slotcount = Counter(corpus).most_common(showcount)
    outlist.append(f'Most common slot layouts (top {show_percent}%):<ul class="nomarg">')
    for x in slotcount:
        #perc = round(x[1] / numfound * 100, 1)
        outlist.append(f'<li>{x[1]}: {", ".join(x[0])}')
    outlist.append('</ul><p>')
    indivslots = Counter(chain.from_iterable(corpus)).most_common(6)
    outlist.append('Most common individual IOs:<ul class="nomarg">')
    for x in indivslots:
        outlist.append(f'<li>{x[1]}: {x[0]}')
    outlist.append('</ul>')
    if showfor: outlist.append('</details>')
    return ''.join(outlist)

def output_data(outfile, archetype, primsec, forum, pwrsets, results):
    """builds HTML output and exports to file"""
    showfor = True if forum == 'all' else False
    pwr_corpus = []
    data = ['<html><style type="text/css">details.indent1{padding-left: 40px;}' +\
            '.nomarg{margin-top:-1em;}</style>']
    data.append(f'<details><summary><b>{archetype} {primsec}</b></summary>')

    for pwrset in pwrsets:
        for setname, pwrlist in pwrset.items():
            data.append(f'<details class="indent1"><summary>{setname}</summary>')
            print(f'Compiling data for {setname}.')
            for pwr in pwrlist:
                if pwr.name not in banned_powers:
                    data.append(f'<details class="indent1"><summary><u>{pwr.name}</u></summary>')
                    if forum in ['hc', 'all']:
                        pwr_corpus = [x.slotting for x in results if x.setname == setname
                                      and x.pwrname == pwr.name and x.forum == 'hc']
                        data.append(generate_pwr_data('hc', pwr_corpus, showfor))
                        if not showfor: data += '</details>'
                    if forum in ['paragon', 'all']:
                        pwr_corpus = [x.slotting for x in results if x.setname == setname
                                      and x.pwrname == pwr.name and x.forum == 'paragon']
                        data.append(generate_pwr_data('paragon', pwr_corpus, showfor) + '</details>')
        data.append('</details>')
    data.append('</details></details></html>')
    with open(outfile, 'w', encoding='utf-8') as output:
        output.write(''.join(data))

def scan_files(pwrsets, indirs):
    slots = []

    for indir in indirs:
        print(f'Scanning {len(listdir(indir))} files in {indir}...')

        for file in listdir(indir):
            try:
                res = parse_file(indir, file, pwrsets)
            except Exception as err:
                print(f'Failed to read file {file} - {err}')
                pass
            else:
                if res:
                    slots.extend(res)
    return slots

def generate_forum_path(archetype, forum):
    """returns correct path for designated forum"""
    outdirs = []
    if forum in ['hc', 'all']:
        if archetype == 'Peacebringer':
            outdirs.append(f'd:\\tmp\\homecoming\\warshade')
        elif archetype in ['Arachnos Soldier', 'Arachnos Widow']:
            outdirs.append(f'd:\\tmp\\homecoming\\widow')
        elif archetype in ['Inherent', 'Pool', 'Epic']:
            outdirs += [x[0] for x in walk('d:\\tmp\\homecoming')] # QQQQ test
            #outdirs.append(f'd:\\tmp\\homecoming\\brute')
        else:
            outdirs.append(f'd:\\tmp\\homecoming\\{archetype.lower()}')
    if forum in ['paragon', 'all']:
        if archetype == 'Sentinel': # no sents in original
            return outdirs
        if archetype in ['Peacebringer', 'Warshade']:
            archetype = 'Kheldian'
        if archetype in ['Arachnos Soldier', 'Arachnos Widow']:
            archetype = 'Soldiers of Arachno' #missing s is deliberate
        if archetype in ['Inherent', 'Pool', 'Epic']:
            outdirs += [x[0] for x in walk('d:\\tmp\\cohtest')] # QQQQ test
            #pass
        else:
            outdirs.append(f'D:\\tmp\\cohtest\\{archetype.capitalize()}s - City of Heroes Forums')
    if not outdirs:
        print(f'Error - forum not recognised: {forum}')
        return None
    return outdirs

def scan_powersets(archetype, p_or_s, targetset=None, forum='hc'):
    results = []
    forum_name = ''
    outname = 'All Sets' if not targetset else targetset

    if archetype not in ['Inherent', 'Pool', 'Epic']:
        primsec = 'Primary' if p_or_s == 1 else 'Secondary'
        if not targetset: primsec = primsec[:-1] + 'ies'
    else:
        primsec = 'Powers'

    if forum == 'hc':
        forum_name = 'Homecoming'
    elif forum == 'paragon':
        forum_name == 'Paragon'
    elif forum == 'all':
        forum_name = 'All Forums'
    else:
        print(f'Unknown forum designation: {forum}')
        return

    indirs = generate_forum_path(archetype, forum)
    data = coh_api_parser.get_category_data(archetype, p_or_s, targetset)
    for archetype, pwrsets in data.items():

        results.extend(scan_files(pwrsets, indirs))
        outfilename = r'k:\Dropbox\tmp\coh\theory\datamine' + '\\' +\
                      f'CoH-{archetype} {primsec}-{outname}-{forum_name}.htm'

        output_data(outfilename, archetype, primsec, forum, pwrsets, results)

def main():
    start = time.time()
    #archetype, primary or secondary, set (None is all sets), forums to search (hc or paragon)
    coh_class = ['Blaster', 'Corruptor', 'Defender', 'Controller', 'Dominator',\
                 'Brute', 'Tanker', 'Scrapper', 'Warshade', 'Peacebringer', 'Sentinel', \
                  'Mastermind', 'Stalker', 'Arachnos Soldier', 'Arachnos Widow']
    '''
    for c in coh_class:
        scan_powersets(c, 1, None, 'all')
        scan_powersets(c, 2, None, 'all')
    '''
    
    #name of archetype or 'Epic' or 'Pool', primary or secondary, targetset=None, forum=hc
    scan_powersets('Epic', 1, None, 'all')

    end = round(time.time() - start)
    print(f'Run finished in {end} secs.')

if __name__ == '__main__':
    main()
