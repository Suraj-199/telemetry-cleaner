import streamlit as st
import pandas as pd
import json
import sys
import os

# Add the root directory to sys.path so 'src' can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline import process_telemetry_file
import src.db as db

st.set_page_config(
    page_title="Telemetry Analytics Platform",
    page_icon="📊",
    layout="wide"
)

# Initialize DB
db.init_db()

# Custom CSS for glassmorphism and modern feel
st.markdown("""
<style>
    /* Premium dark theme inspired */
    .stApp {
        background-color: #0d121c; /* Deep navy */
        color: #f2f2f2;
    }
    
    .stButton>button {
        background: rgba(40, 160, 255, 0.2);
        border: 1px solid rgba(40, 160, 255, 0.4);
        border-radius: 8px;
        color: white;
        transition: all 0.2s;
    }
    
    .stButton>button:hover {
        background: rgba(40, 160, 255, 0.4);
        border-color: rgba(40, 160, 255, 0.6);
    }
    
    .glass-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 20px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# Navigation
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", [
    "📊 Dashboard", 
    "📥 Upload & Process", 
    "🔧 Metric Mappings",
    "🌐 Network Mappings",
    "⚙️ Report Configs"
])

if page == "📊 Dashboard":
    st.title("Generic Telecom Telemetry Analytics")
    st.markdown('<div class="glass-card"><h3>Welcome to the Analytics Platform</h3><p>Use the navigation on the left to configure mappings or upload raw telemetry files.</p></div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown('<div class="glass-card"><h4>Active Platforms</h4><p>2</p></div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="glass-card"><h4>Report Configs</h4><p>{len(db.get_report_configs())}</p></div>', unsafe_allow_html=True)
    with col3:
         st.markdown(f'<div class="glass-card"><h4>Metric Mappings</h4><p>{len(db.get_metric_mappings())}</p></div>', unsafe_allow_html=True)


elif page == "📥 Upload & Process":
    st.title("Upload & Process Telemetry")
    
    configs = db.get_report_configs()
    config_opts = {c['name']: c['id'] for c in configs}
    selected_config_name = st.selectbox("Select Report Configuration", list(config_opts.keys()))
    
    uploaded_file = st.file_uploader("Upload Raw Data (Excel or CSV)", type=['xlsx', 'csv'])
    
    if uploaded_file is not None:
        if st.button("Run Processing Pipeline"):
            with st.spinner("Processing telemetry data..."):
                try:
                    output_bytes, preview_df = process_telemetry_file(
                        uploaded_file, 
                        uploaded_file.name, 
                        report_config_id=config_opts[selected_config_name]
                    )
                    
                    if output_bytes:
                        st.success("Processing complete!")
                        
                        st.subheader("Preview Results")
                        st.dataframe(preview_df.head(20))
                        
                        st.download_button(
                            label="📥 Download Analyzed Report (Excel)",
                            data=output_bytes,
                            file_name=f"Analyzed_{uploaded_file.name.split('.')[0]}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.warning("No data was processed. Check if the file matches the expected structure.")
                except Exception as e:
                    st.error(f"An error occurred during processing: {e}")

elif page == "🔧 Metric Mappings":
    st.title("Metric Mappings Configuration")
    
    mappings = db.get_metric_mappings()
    
    # Display current mappings
    st.subheader("Current Mappings")
    if mappings:
        df_maps = pd.DataFrame([
            {"Source Metric": k[0], "Platform": k[1], "Normalized Metric": v}
            for k, v in mappings.items()
        ])
        st.dataframe(df_maps, use_container_width=True)
    
    st.subheader("Add New Mapping")
    with st.form("new_metric_mapping"):
        col1, col2, col3 = st.columns(3)
        with col1:
            src = st.text_input("Source Metric")
        with col2:
            plat = st.text_input("Platform (Leave blank for ALL)")
        with col3:
            norm = st.text_input("Normalized Metric")
            
        submitted = st.form_submit_button("Add Mapping")
        if submitted and src and norm:
            with db.get_db_connection() as conn:
                try:
                    conn.execute(
                        "INSERT INTO metric_mappings (source_metric, platform, normalized_metric) VALUES (?, ?, ?)",
                        (src, plat if plat else None, norm)
                    )
                    conn.commit()
                    st.success("Mapping added!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding mapping: {e}")

elif page == "🌐 Network Mappings":
    st.title("Network Mappings Configuration")
    
    mappings = db.get_network_mappings()
    
    # Display current mappings
    st.subheader("Current Mappings")
    if mappings:
        df_maps = pd.DataFrame([
            {"Raw Network Value": k, "Normalized Network Value": v}
            for k, v in mappings.items()
        ])
        st.dataframe(df_maps, use_container_width=True)
        
elif page == "⚙️ Report Configs":
    st.title("Report Configurations")
    configs = db.get_report_configs()
    
    st.subheader("Active Configurations")
    for c in configs:
        with st.expander(c['name']):
            st.write(f"**Description:** {c['description']}")
            st.write(f"**Group By:** {c['group_by']}")
            st.write(f"**Statistics:** {c['statistics']}")
            st.write(f"**Filters:** {c['filters']}")

    st.subheader("Create New Configuration")
    with st.form("new_report_config"):
        name = st.text_input("Name", placeholder="e.g., All Sections Full Report")
        desc = st.text_input("Description", placeholder="e.g., Groups by screen, platform, network for all sections")
        
        # We need multiselect for lists
        group_by = st.multiselect(
            "Group By Dimensions", 
            ['normalized_trace_name', 'platform', 'network_type', 'section'],
            default=['normalized_trace_name', 'platform', 'network_type']
        )
        
        stats = st.multiselect(
            "Statistics to Calculate",
            ['count', 'p50', 'p75', 'p90', 'p95', 'p99', 'mean', 'median', 'min', 'max', 'std'],
            default=['p75', 'p90']
        )
        
        filters_str = st.text_area("Filters (JSON format, optional)", placeholder='e.g., {"section": "Screen Metrics"} or leave blank for all data')
        
        submitted = st.form_submit_button("Create Configuration")
        if submitted and name and group_by and stats:
            filters_obj = {}
            if filters_str.strip():
                try:
                    filters_obj = json.loads(filters_str)
                except Exception as e:
                    st.error(f"Invalid JSON in filters: {e}")
                    st.stop()
                    
            with db.get_db_connection() as conn:
                try:
                    conn.execute(
                        '''INSERT INTO report_configs (name, description, group_by, statistics, filters) 
                           VALUES (?, ?, ?, ?, ?)''',
                        (name, desc, json.dumps(group_by), json.dumps(stats), json.dumps(filters_obj))
                    )
                    conn.commit()
                    st.success("Report Configuration created!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error creating configuration: {e}")
