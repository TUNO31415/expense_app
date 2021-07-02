import discord
import csv
import utilities
from datetime import datetime
import options
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
        input_msg = message.content.split(" ")
        if len(input_msg) != 4:
            await message.channel.send('フォーマットが違うよ！')
            return

        # format date
        date_num = input_msg[1].split("-")
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
        stats = options.check_expense()
        if "y" in message.content:
            yearly_stats = utilities.calculate_yearly(stats)
            res_str = ""
            for (year, amount) in yearly_stats:
                res_str += str(year) + " : € " + str(amount * -1) + "\n"
            await message.channel.send("**Yearly stats**")
            await message.channel.send(res_str)
            return
        else:
            montly_stats = utilities.calculate_monthly(stats)
            res_str = ""
            for (year, month, amount) in montly_stats:
                # res_str += str(year) + " " + str(utilities.month_to_name(month)) + " : € " + str(amount * -1) + "\n"
                res_str += str(year) + "/" + str(month) + " : € " + str(amount * -1) + "\n"
            await message.channel.send("**Monthly stats**")
            await message.channel.send(res_str)
            return 
        
    if message.content.startswith('help'):
        await message.channel.send("**Expense input** : \n exp date category price \n *Category list* \n f : Food, \n t : Transportation,\n e : Extertainment,\n n : Necessities,\n h : Housing expense \n e.g) exp 2021-6-12 f 10.95" )
        await message.channel.send("**Check stats** : \n stats (for checking monthly stats) \n stats y (for checking yearly stats)\n")
        return     
   
client.run("ODYwNDQ0MTgyMTM3Mjc0MzY4.YN7VFw.-LFLV7KyPUbwwYz_vrqxdXVEJcg")



