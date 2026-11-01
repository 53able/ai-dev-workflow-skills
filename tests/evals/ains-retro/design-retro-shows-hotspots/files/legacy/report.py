# 月次売上レポート（2019年の集計バッチから移植）
# d: [(日付 'YYYY-MM-DD', sku, 単価, 数量), ...]  m: 'YYYY-MM' で絞る  f: 1 なら CSV
def r(d, m=None, f=0):
    o = {}
    for x in d:
        if m and x[0][:7] != m:
            continue
        k = x[1]
        if k not in o:
            o[k] = [0, 0]
        o[k][0] = o[k][0] + x[2] * x[3]
        o[k][1] = o[k][1] + x[3]
    t = 0
    s = ''
    for k in sorted(o):
        t = t + o[k][0]
        if f == 1:
            s = s + k + ',' + str(o[k][0]) + ',' + str(o[k][1]) + '\n'
        else:
            s = s + k + '\t' + str(o[k][0]) + '\t' + str(o[k][1]) + '\n'
    if f == 1:
        s = s + 'TOTAL,' + str(t) + '\n'
    else:
        s = s + 'TOTAL\t' + str(t) + '\n'
    return s
