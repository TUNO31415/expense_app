import utilities
import csv
from datetime import datetime

def input_saving():
    while(True):
        amount_input = input("How much do you have? : ")

        if utilities.check_number(amount_input):
            #input to csv file
            amount = float(amount_input)
            today = datetime.date.today()

            with open('data.csv', 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([today.strftime("%Y-%m-%d"), "Saving", amount, "", True])

            print("***Successfully saved!***")
            print("")
            break
        else:
            print("Please input the correct numerical value")

def input_expense():
    while(True):

        amount_input = input("How much did you spend? : ")

        if(utilities.check_number(amount_input)):
            amount = float(amount_input)

            while(True):
                
                print("---- Which category? (Select number) ----")
                print("0 : Food")
                print("1 : Transportation")
                print("2 : Extertainment")
                print("3 : Other shopping")
                print("4 : Housing expense")
                cat_input = input()
                cat = ""
                if(utilities.check_number(cat_input)):
                    cat = utilities.categorize(int(cat_input))
                    break
                else :
                    print("Try again")

            while(True):

                # Here must be input(). Because it should be tuple
                date_input = input("Date (dd,mm,yyyy) : ")
                date_num = date_input.split(",")

                try:
                    date = utilities.format_date(date_num)
                    break
                except:
                    print("Incorrect format try again")

            comment = input('Comments : ')
            
            print("------------------------------------")
            print("Input")
            print("Amount : " + str(amount))
            print("Category : " + str(cat))
            print("Date : " + date.strftime("%Y-%m-%d"))
            print("Comment : " + str(comment))

            confirm = input("Confirm? y/n : ")
            if(confirm == "y"):

                with open('data.csv', 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([date.strftime("%Y-%m-%d"), cat, -1*amount, comment, False])

                print("***Successfully saved!***")
                print("")

                option_input = input("Do you wish to add another data? [y/n]")

                if(option_input == 'y'):
                    continue

                break

            else:
                print("")

        else:
            print("Please provide correct numerical value")


def check_expense():

    data = []

    with open('data.csv') as csv_data :
        csv_reader = csv.reader(csv_data, delimiter=',')
        line_count = 0

        for row in csv_reader:
            if line_count == 0:
                line_count += 1
                continue
            else :
                if row[4] == "False":
                    date = datetime.strptime(row[0], "%Y-%m-%d")
                    amount = float(row[2])
                    data.append((date, amount))
    # print(data)
    return  data