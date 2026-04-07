import streamlit as st
import pandas as pd

# 1. Establish Snowflake Connection
# In Streamlit Cloud/Local, you define these in .streamlit/secrets.toml
conn = st.connection("snowflake")

st.title("OAF Malawi: IDS Generator")

# 2. Sidebar Filters (Non-Technical UI)
st.sidebar.header("Delivery Filters")

# Fetch unique sites for the dropdown (efficiently)
@st.cache_data
def get_site_list():
    query = "SELECT DISTINCT SITE FROM DEVELOPMENT.SEASON_CLIENTS_LR25.INPUT_DELIVERY_TABLE ORDER BY SITE"
    return conn.query(query)

sites = get_site_list()
selected_site = st.sidebar.selectbox("Select Site Name", sites)

if selected_site:
    # 3. Pull ONLY the data for the selected site
    # This prevents lag by only pulling ~100 rows instead of 1M
    query = f"""
        SELECT ACCOUNT, CLIENT, SHORTNAME, QUANTITY 
        FROM DEVELOPMENT.SEASON_CLIENTS_LR25.INPUT_DELIVERY_TABLE 
        WHERE SITE = '{selected_site}' 
        AND STATUS = 'Undelivered'
    """
    raw_data = conn.query(query)

    if not raw_data.empty:
        # 4. Transform Logic (Pivot)
        pivot_df = raw_data.pivot_table(
            index=['ACCOUNT', 'CLIENT'], 
            columns='SHORTNAME', 
            values='QUANTITY', 
            aggfunc='sum'
        ).fillna(0)

        # Convert to POD format (1s and blanks)
        pod_display = pivot_df.applymap(lambda x: '1' if x > 0 else '')

        # 5. Insert "Delivery Adjustment" rows
        final_rows = []
        for idx, row in pod_display.iterrows():
            # Farmer Row
            row_dict = row.to_dict()
            row_dict['Account'] = idx[0]
            row_dict['Farmer Name'] = idx[1]
            final_rows.append(row_dict)
            
            # Adjustment Row
            adj_row = {col: '' for col in pod_display.columns}
            adj_row['Account'] = ''
            adj_row['Farmer Name'] = '— Delivery Adjustment'
            final_rows.append(adj_row)

        final_ids = pd.DataFrame(final_rows)
        
        # Display Preview in UI
        st.subheader(f"Preview for {selected_site}")
        st.write(final_ids)

        # 6. Placeholder for PDF Generation
        if st.button("Generate Printable PDF"):
            st.info("Generating PDF... (This would trigger the ReportLab/FPDF function)")
    else:
        st.warning("No undelivered orders found for this site.")