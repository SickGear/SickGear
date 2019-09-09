import sys

print('Args:', sys.argv)

if 7 != len(sys.argv):
    print('ERROR')
    exit()
else:
    try:
        int(sys.argv[3])
        int(sys.argv[4])
        int(sys.argv[5])
    except Exception as e:
        print(e)
        print('ERROR')
        exit()

print('SUCCESS')
