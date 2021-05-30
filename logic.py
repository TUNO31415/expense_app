import utilities
import csv
import datetime

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

def categorize(cat_num):
    cat = {
        0 : "Food",
        1 : "Transportation",
        2 : "Extertainment",
        3 : "Necessities",
        4 : "Housing expense"
    }
    
    return cat.get(cat_num, "Others")

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
                    cat = categorize(int(cat_input))
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