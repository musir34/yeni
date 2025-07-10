import itertools,io 
with io.open('templates/base.html','r',encoding='utf-8') as f: 
lines = f.readlines() 
for i,line in enumerate(lines): 
    if 'container mt-5' in line: 
        print(i+1,repr(line)) 
