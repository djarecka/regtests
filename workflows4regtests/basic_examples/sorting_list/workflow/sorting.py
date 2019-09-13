import json, os

def sorting(filename, outputdir):
    """ a simple function for sorting list"""
    with open(filename) as json_data:
        list2sort = json.load(json_data)

    list2sort.sort()
    file_sort = os.path.join(outputdir, 'list_sorted.json')
    file_sum = os.path.join(outputdir, 'sum_list.json')


    with open(file_sort, 'w') as outfile:
        json.dump(list2sort, outfile)
    with open(file_sum, "w") as outfile:
        json.dump(sum(list2sort), outfile)

    if not os.path.exists(file_sort):
        raise Exception
    if not os.path.exists(file_sum):
        raise Exception

    print(outputdir, os.path.exists(file_sort), os.path.exists(file_sum))


if __name__ == '__main__':
    from argparse import ArgumentParser, RawTextHelpFormatter
    parser = ArgumentParser(description=__doc__,
                            formatter_class=RawTextHelpFormatter)
    parser.add_argument("-f", dest="filename",
                        help="file with a list to sort")
    parser.add_argument("-o", dest="outputdir",
                        help="directory with the output")
    args = parser.parse_args()

    sorting(args.filename, args.outputdir)
