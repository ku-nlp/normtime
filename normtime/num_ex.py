#coding: utf-8

def str2num(string):
    """ stringに対応する数値(str)またはNoneを返す """
    digit_list = get_digit_list(string)
    if None in digit_list: 
        return None
    len_digit_list = len(digit_list)
    for i,num in enumerate(digit_list[::-1]):
        if num == None:
            digit_list.pop(len_digit_list-i-1)
    return make_num(digit_list)


def make_num(num_list):
    ### 十、百、千を含む場合: ex)二百三十年
    if not num_list:
        return 
    if max(num_list) > 9:
        keta_list = [0,0,0,0]
        tmp_num = None
        firstFlag = 1 # 百二十年の「百」を認識するためのフラグ
        for num in num_list:
            if num == -1: # 数,何
                tmp_num = "X"
            elif num == 1000:
                if firstFlag and tmp_num == None:
                    keta_list[3] = 1
                else: 
                    if tmp_num != None: keta_list[3] = tmp_num
                    else: keta_list[3] = 1
                tmp_num = None
                firstFlag = 0
            elif num == 100:
                if firstFlag and tmp_num == None:
                    keta_list[2] = 1
                else: 
                    if tmp_num != None: keta_list[2] = tmp_num
                    else: keta_list[2] = 1
                tmp_num = None
                firstFlag = 0
            elif num == 10:
                if firstFlag and tmp_num == None:
                    keta_list[1] = 1
                else: 
                    if tmp_num != None: keta_list[1] = tmp_num
                    else: keta_list[1] = 1
                tmp_num = None
                firstFlag = 0
            else: # 0-9
                tmp_num = num
        if tmp_num != None: 
            keta_list[0] = tmp_num

        num = 0
        for keta, i in enumerate(keta_list):
            if i != 'X':
                num += i * (10**keta)
            else:
                num += 1 * (10**keta)
        nums = [x for x in str(num)]
        for keta, i in enumerate(keta_list):
            if i == 'X':
                nums[len(nums)-1-keta] = 'X'
        return ''.join(nums)
    ### 数値のみの場合: ex)1923年
    if min(num_list) >= -1 and max(num_list) <= 9:
        num = 0
        for keta, tmpnum in enumerate(num_list[::-1]):
            if tmpnum != -1:
                num += tmpnum* (10**keta)
        nums = [x for x in str(num)]
        for keta, tmpnum in enumerate(num_list[::-1]):
            if tmpnum == -1:
                nums[len(nums)-1-keta] = 'X'
        num = ''.join(nums)
        if num_list[0] == 0 and len(num_list) > 1:
            return "0"+str(num)
        return str(num)
    # Noneを含む場合
    num_list = [x for x in num_list if x != None]
    if len(num_list) > 0 and min(num_list) >= 0 and max(num_list) <= 9:
        num = 0
        for keta, tmpnum in enumerate(num_list[::-1]):
            num += tmpnum* (10**keta)
        return str(num)


def get_digit_list(uni_strings):
    digit_list = []
    zeroFlag = False
    for uni_string in uni_strings:
        num = None
        if uni_string == u'0' or uni_string == u'０' or uni_string == u'〇' or uni_string == u'零': num = 0
        elif uni_string == u'1' or uni_string == u'１' or uni_string == u'一': num = 1
        elif uni_string == u'2' or uni_string == u'２' or uni_string == u'二': num = 2
        elif uni_string == u'3' or uni_string == u'３' or uni_string == u'三': num = 3
        elif uni_string == u'4' or uni_string == u'４' or uni_string == u'四': num = 4
        elif uni_string == u'5' or uni_string == u'５' or uni_string == u'五': num = 5
        elif uni_string == u'6' or uni_string == u'６' or uni_string == u'六': num = 6
        elif uni_string == u'7' or uni_string == u'７' or uni_string == u'七': num = 7
        elif uni_string == u'8' or uni_string == u'８' or uni_string == u'八': num = 8
        elif uni_string == u'9' or uni_string == u'９' or uni_string == u'九': num = 9
        elif uni_string == u'十': num = 10
        elif uni_string == u'百': num = 100
        elif uni_string == u'千': num = 1000
        elif uni_string in [u'数',u'何']: num = -1

        if uni_string == u'ゼ': 
            zeroFlag = True
            continue
        elif uni_string == u'ロ' and zeroFlag: 
            num, zeroFlag = 0, False
        elif zeroFlag: 
            zeroFlag = False
        digit_list.append(num)
    return digit_list


if __name__ == '__main__':
    print(str2num(u'二百三十年'))
    print(str2num(u'二年'))
    print(str2num(u'二'))
    print(str2num(u'二百三十'))
    print(str2num(u'二〇〇三'))
    print(str2num(u'２００１'))
    print(str2num(u'ゼロ'))
    print(str2num(u'十数'))
    print(str2num(u'数十'))
    print(str2num(u'数'))
    print(str2num(u'００'))
    print(str2num(u'0.5'))
    print(str2num(u'あおい'))
    print(str2num(u'二言'))
    print(str2num(u'１２：００'))

    print(get_digit_list(u'二百三十年'))
    print(get_digit_list(u'二年'))
    print(get_digit_list(u'二'))
    print(get_digit_list(u'二百三十'))
    print(get_digit_list(u'ゼロ歳'))
    print(get_digit_list(u'十数年前'))
    print(get_digit_list(u'あおい'))
    print(get_digit_list(u'二言'))
    print(get_digit_list(u'数年'))
