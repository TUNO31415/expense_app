import utilities
import logic
import sys

def operation_switch(n):
    if(n == 1): #Input saving
        logic.input_saving()
    if(n == 2): #Input expense
        logic.input_expense()
    if(n == 3): #Check expense
        logic.check_expense()
    if(n == 4): #Exit
        sys.exit()

print("Welcome to expenditure app")

while(True):
    print("===========++Main Menu++===========")
    print("1 : Input your savings")
    print("2 : Input your expense")
    print("3 : Check your statistics")
    print("4 : Exit")
    print("====================================")

    option = input("Select option : ")

    if utilities.check_number(option):
        operation_switch(int(option))
        continue
    else:
        print("")
        print("Please choose the correct option")
        






