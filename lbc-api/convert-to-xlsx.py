import pandas as pd
import os

# Read the CSV file
csv_path = 'lbc-rates.csv'
xlsx_path = 'lbc-rates.xlsx'

# Check if CSV exists
if not os.path.exists(csv_path):
    print(f"Error: {csv_path} not found")
    exit(1)

# Read CSV
print(f"Reading {csv_path}...")
df = pd.read_csv(csv_path)

# Clean up column names
df.columns = df.columns.str.strip()

# Create Excel writer with multiple sheets
print(f"Creating {xlsx_path}...")
with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
    # Sheet 1: All Data
    df.to_excel(writer, sheet_name='All Rates', index=False)
    
    # Sheet 2: Metro Manila only
    metro_manila = df[df['Destination'].isin([
        'Manila', 'Quezon City', 'Makati', 'Pasig', 'Taguig', 'Mandaluyong',
        'Pasay', 'Caloocan', 'Las Piñas', 'Malabon', 'Muntinlupa', 'Navotas',
        'Parañaque', 'San Juan', 'Valenzuela', 'Marikina'
    ])]
    metro_manila.to_excel(writer, sheet_name='Metro Manila', index=False)
    
    # Sheet 3: Luzon Provincial
    luzon_cities = [
        'Baguio', 'Angeles', 'Olongapo', 'Batangas City', 'Lipa', 'Lucena',
        'Naga', 'Legazpi', 'Sorsogon', 'Masbate', 'Tuguegarao', 'Laoag',
        'Vigan', 'San Fernando (La Union)', 'Dagupan', 'Urdaneta',
        'Cabanatuan', 'San Jose del Monte', 'Malolos', 'Meycauayan',
        'San Pablo', 'Calamba', 'Santa Rosa', 'Biñan', 'San Pedro',
        'Dasmariñas', 'General Trias', 'Imus', 'Bacoor', 'Trece Martires',
        'Tanauan', 'Talisay', 'Toledo'
    ]
    luzon = df[df['Destination'].isin(luzon_cities)]
    luzon.to_excel(writer, sheet_name='Luzon Provincial', index=False)
    
    # Sheet 4: Visayas
    visayas_cities = [
        'Cebu City', 'Mandaue', 'Lapu-Lapu', 'Talisay (Cebu)', 'Danao',
        'Iloilo City', 'Bacolod', 'Tacloban', 'Ormoc', 'Calbayog',
        'Tagbilaran', 'Dumaguete', 'Roxas', 'Kabankalan', 'San Carlos',
        'Bogo', 'Carcar'
    ]
    visayas = df[df['Destination'].isin(visayas_cities)]
    visayas.to_excel(writer, sheet_name='Visayas', index=False)
    
    # Sheet 5: Mindanao
    mindanao_cities = [
        'Davao City', 'Cagayan de Oro', 'General Santos', 'Zamboanga City',
        'Butuan', 'Iligan', 'Ozamiz', 'Pagadian', 'Dipolog', 'Tandag',
        'Surigao', 'Cotabato', 'Koronadal', 'Valencia', 'Malaybalay'
    ]
    mindanao = df[df['Destination'].isin(mindanao_cities)]
    mindanao.to_excel(writer, sheet_name='Mindanao', index=False)
    
    # Sheet 6: Summary by Region
    summary_data = []
    for declared_value in [100, 500, 1000, 2000, 3000, 5000]:
        # Metro Manila
        mm = df[(df['Declared Value'] == declared_value) & (df['Destination'].isin([
            'Manila', 'Quezon City', 'Makati', 'Pasig', 'Taguig'
        ]))]
        if not mm.empty:
            summary_data.append({
                'Region': 'Metro Manila',
                'Declared Value': declared_value,
                'Average Total': mm['Total'].mean(),
                'Min Total': mm['Total'].min(),
                'Max Total': mm['Total'].max(),
                'Cities': len(mm['Destination'].unique())
            })
        
        # Luzon Provincial
        luzon_df = df[(df['Declared Value'] == declared_value) & (df['Destination'].isin(luzon_cities))]
        if not luzon_df.empty:
            summary_data.append({
                'Region': 'Luzon Provincial',
                'Declared Value': declared_value,
                'Average Total': luzon_df['Total'].mean(),
                'Min Total': luzon_df['Total'].min(),
                'Max Total': luzon_df['Total'].max(),
                'Cities': len(luzon_df['Destination'].unique())
            })
        
        # Visayas
        visayas_df = df[(df['Declared Value'] == declared_value) & (df['Destination'].isin(visayas_cities))]
        if not visayas_df.empty:
            summary_data.append({
                'Region': 'Visayas',
                'Declared Value': declared_value,
                'Average Total': visayas_df['Total'].mean(),
                'Min Total': visayas_df['Total'].min(),
                'Max Total': visayas_df['Total'].max(),
                'Cities': len(visayas_df['Destination'].unique())
            })
        
        # Mindanao
        mindanao_df = df[(df['Declared Value'] == declared_value) & (df['Destination'].isin(mindanao_cities))]
        if not mindanao_df.empty:
            summary_data.append({
                'Region': 'Mindanao',
                'Declared Value': declared_value,
                'Average Total': mindanao_df['Total'].mean(),
                'Min Total': mindanao_df['Total'].min(),
                'Max Total': mindanao_df['Total'].max(),
                'Cities': len(mindanao_df['Destination'].unique())
            })
    
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_excel(writer, sheet_name='Summary by Region', index=False)

print(f"✅ Successfully created {xlsx_path}")
print(f"📊 Total sheets: 6")
print(f"📈 Total records: {len(df)}")

# Print summary
print("\n📋 Summary:")
print(f"  - All Rates: {len(df)} records")
print(f"  - Metro Manila: {len(metro_manila)} records")
print(f"  - Luzon Provincial: {len(luzon)} records")
print(f"  - Visayas: {len(visayas)} records")
print(f"  - Mindanao: {len(mindanao)} records")
print(f"  - Summary: {len(summary_df)} records")