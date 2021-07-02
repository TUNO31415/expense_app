import discord
import csv
import utilities
from datetime import datetime
import os

client = discord.Client()

@client.event
async def on_ready():
    print('We have logged in as {0.user}'.format(client))

@client.event
async def on_message(message):
    # if message.author == client.user:
    #     return

    if message.content.startswith('$hello'):
 
        await message.channel.send('やっほー！みっくだよ')


    if message.content.startswith('exp'):
        # date, category, price
        # e.g) exp 2021-6-12 f 10.95
        # 'f' : "Food",
        # 't' : "Transportation",
        # 'e' : "Extertainment",
        # 'n' : "Necessities",
        # 'h' : "Housing expense"
        input_msg = message.content.split(" ")
        if len(input_msg) != 4:
            await message.channel.send('フォーマットが違うよ！')
            return

        # format date
        date_num = input_msg[1].split("-")
        print(input_msg[1])
        print(date_num)
        try:
            date = utilities.format_date_discord(date_num)
        except:
            await message.channel.send("日付のフォーマットが違うよ！")
            return         

        with open('data.csv', 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([date.strftime("%Y-%m-%d"), utilities.categorize_discord(input_msg[2]), -1*float(input_msg[3]), "", False])
                    await message.channel.send("セーブ完了！お疲れ様！")

        return 

    if message.content.startswith('stats'):
        # show stats
        return 
        
client.run("ODYwNDQ0MTgyMTM3Mjc0MzY4.YN7VFw.-LFLV7KyPUbwwYz_vrqxdXVEJcg")



