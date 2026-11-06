from matplotlib import pyplot as plt
import pandas as pd
import numpy as np

file_path = 'Archive/DataFiles/21incyallagi.csv'

county = 'Fayette County'
state = 'GA'

county = 'Los Angeles County'
state = 'CA'

cols = ['STATEFIPS', 'STATE', 'COUNTYFIPS', 'COUNTYNAME', 'agi_stub', 'N1', 'N2', 'A00100', 'N19300', 'N18800']

brackets = ['Under $1', '$1-10k', '$10k-25k', '$25k-50k', '$50k-75k', '$75k-100k', '$100k-200k', '$200k+']

column_dict = {'N1': 'Number of Returns',
               'N2': 'Number of Individuals',
               'A00100': 'Total AGI Collected',
               'N19300': 'Returns w/ Mortgage',
               'N18800': 'Returns w/ Personal Property Tax'}


agi_dict = {}


for i in range(len(brackets)):
    agi_dict[str(i+1)] = brackets[i]



# df = pd.read_csv(file_path, usecols=cols)
df = pd.read_csv(file_path, encoding="ISO-8859-1")

subframe = df[(df['STATE'] == state) & (df['COUNTYNAME'] == county)]


print(subframe)

fig = plt.figure(figsize=(8,8))
ax1 = fig.add_subplot(111)
ax2 = ax1.twinx()

avg_incomes = np.divide(subframe['A02650'].to_numpy(), subframe['N1'].to_numpy())
avg_incomes[avg_incomes < 0] = 0
print(avg_incomes)

data = {'Brackets': brackets,
        'Num Returns': subframe['N1'].to_numpy(),
        'Avg AGI': avg_incomes}

new_df = pd.DataFrame(data=data)
new_df = new_df.set_index('Brackets', drop=False)

# plt.bar(x=brackets, height=subframe['N1'].to_numpy(), ax=ax1)
# plt.bar(x=brackets, height=avg_incomes, ax=ax2)

new_df['Num Returns'].plot(kind='bar', color='red', ax=ax1, position=1, width=.2)
new_df['Avg AGI'].plot(kind='bar', color='blue', ax=ax2, position=0, width=.2)

tot_returns = np.sum(new_df['Num Returns'].to_numpy())
tot_agi = np.sum(subframe['A02650'].to_numpy())
tot_avg_agi = tot_agi/tot_returns

print(tot_returns)
print(tot_avg_agi)

ax1.set_title(f'Tax Return and Income Breakdown {county}')
ax1.set_xlabel('AGI Bracket')
ax1.set_ylabel('Number of Returns')
ax1.tick_params(axis='x', labelrotation=30)

ax2.set_ylabel('Average Gross Income ($1k)')

plt.xticks(ha='right')
plt.show()

