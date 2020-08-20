# Japanese Temporal Expression Normalizer 

## Requirements  
 - python >= 3.6 

## Install 
```
% python setup.py install 
```

## Usage 

```Python
from normtime import normalize
print(normalize('来年4/26', TYPE='DATE', dct='2013-06-01'))
```

### Predicting using file

Note that the delimiter is tab.  
--dct represents document creation day.  
When --dct is ommited, today is regarded as dct.

```
% cat test.txt
来月出張する
	0	2	DATE

明日出張する
	0	2	DATE

100日後出張する
	0	5	DATE

20時に出る。5時間後に会う。
	0	3	TIME
	7	11	TIME

% python3 tools/evaluate.py -t test.txt --dct 2019-06-24
来月	XXXX-XX	2019-07
明日	XXXX-XX-XX	2019-06-25
100日後	Q+100D	2019-10-03
20時	XXXX-XX-XXT20	2019-06-24T20
5時間後	Q+5H	2019-06-24T25
```


### Evaluation by BCCWJ-TimeBank 

```
% python3  tools/evaluate.py -x  /loquat/sakaguchi/BCCWJ-TimeBank/2016_saka/BCCWJ-TIMEX/xmldata  
```
