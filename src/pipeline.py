import pandas as pd
import numpy as np
import os
import io
import json
from datetime import datetime

import src.db as db

def process_telemetry_file(file_obj, filename, report_config_id=1):
    """
    Main processing pipeline.
    """
    db.init_db() # Ensure DB is initialized
    
    # 1. Read file
    if filename.endswith('.csv'):
        # Just put it in a dict to mimic excel sheet structure
        sheets = {'Sheet1': pd.read_csv(file_obj)}
    else:
        xls = pd.ExcelFile(file_obj)
        sheets = {sheet_name: pd.read_excel(xls, sheet_name=sheet_name) for sheet_name in xls.sheet_names}

    # Load mappings
    platform_rules = db.get_platform_rules()
    network_mappings = db.get_network_mappings()
    metric_mappings = db.get_metric_mappings()
    trace_prefixes = db.get_trace_prefixes()
    report_configs = db.get_report_configs()
    
    config = next((c for c in report_configs if c['id'] == report_config_id), None)
    if not config:
        raise ValueError(f"Report Config ID {report_config_id} not found.")

    group_by_cols = json.loads(config['group_by'])
    statistics_to_calc = json.loads(config['statistics'])
    filters = json.loads(config['filters']) if config['filters'] else {}

    all_cleaned_records = []
    
    for sheet_name, df in sheets.items():
        if df.empty:
            continue
            
        # 2. Determine Platform
        # Use sheet name directly for platform
        platform = str(sheet_name).strip()
        
        # Determine internal normalized platform for metric mapping lookups
        normalized_platform = 'Unknown'
        for rule in platform_rules:
            if rule['pattern'].lower() in sheet_name.lower():
                normalized_platform = rule['platform']
                break

        # 3. Basic Cleaning
        # Assume generic structure for now, matching the examples: section, trace_name, metric_name, value, radio_type etc.
        # Check required canonical columns exists. If not, map or skip.
        required_cols = ['trace_name', 'metric_name', 'value', 'radio_type']
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
             # Skip sheets that don't match the canonical structure
             print(f"Skipping sheet {sheet_name} due to missing columns: {missing_cols}")
             continue
        
        # Remove null values in 'value'
        df = df.dropna(subset=['value'])
        
        # Ensure it's numeric
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna(subset=['value'])
        
        # 4. Normalization
        
        # Add original rows to keep for traceability before we modify them heavily
        # Pandas index corresponds to original row (approximately, +2 for excel headers usually)
        df['source_row'] = df.index + 2 
        df['source_sheet'] = sheet_name
        df['platform'] = platform
        df['normalized_platform'] = normalized_platform

        # Fill NaN trace names with the section name (e.g., app_cold_start) so they aren't dropped
        df['trace_name'] = df['trace_name'].fillna(df['section'])

        # Trace Name Normalization
        def normalize_trace(trace):
            if pd.isna(trace) or not isinstance(trace, str):
                return str(trace)
            for prefix in trace_prefixes:
                if trace.startswith(prefix):
                    return trace[len(prefix):]
            return trace
            
        df['normalized_trace_name'] = df['trace_name'].apply(normalize_trace)
        
        # Network Normalization
        def normalize_network(net):
            if pd.isna(net):
                return 'undefined'
            if not isinstance(net, str):
                net = str(net)
            return network_mappings.get(net.upper(), 'undefined')
            
        df['network_type'] = df['radio_type'].apply(normalize_network)

        # Metric Normalization
        def normalize_metric(row):
            m = row['metric_name']
            p = row['normalized_platform']
            
            # Check specific platform mapping first
            if (m, p) in metric_mappings:
                return metric_mappings[(m, p)]
            # Check ALL platforms mapping
            if (m, 'ALL') in metric_mappings:
                return metric_mappings[(m, 'ALL')]
            # If no mapping, just use original
            return m
            
        df['normalized_metric'] = df.apply(normalize_metric, axis=1)

        # Handle Date fields if present
        if 'date' in df.columns:
             # Just keep it as string for min/max
             df['record_date'] = df['date'].astype(str)
        else:
             df['record_date'] = None

        all_cleaned_records.append(df)

    if not all_cleaned_records:
        return None, None

    # Combine all sheets
    master_df = pd.concat(all_cleaned_records, ignore_index=True)
    
    # 5. Apply Filters based on report config
    for col, val in filters.items():
        if col in master_df.columns:
            master_df = master_df[master_df[col] == val]

    if master_df.empty:
        return None, None
        
    # 6. Aggregation & Statistics
    
    # We want to group by user specified dimensions, AND the normalized metric to calculate stats for each metric
    agg_groupby = group_by_cols + ['normalized_metric']
    
    grouped = master_df.groupby(agg_groupby)

    # Calculate stats
    # Prepare mapping for pandas agg
    agg_funcs = {}
    if 'p50' in statistics_to_calc or 'median' in statistics_to_calc:
         agg_funcs['p50'] = pd.NamedAgg(column='value', aggfunc=lambda x: np.percentile(x.dropna(), 50) if not x.dropna().empty else np.nan)
    if 'p75' in statistics_to_calc:
         agg_funcs['p75'] = pd.NamedAgg(column='value', aggfunc=lambda x: np.percentile(x.dropna(), 75) if not x.dropna().empty else np.nan)
    if 'p90' in statistics_to_calc:
         agg_funcs['p90'] = pd.NamedAgg(column='value', aggfunc=lambda x: np.percentile(x.dropna(), 90) if not x.dropna().empty else np.nan)
    if 'p95' in statistics_to_calc:
         agg_funcs['p95'] = pd.NamedAgg(column='value', aggfunc=lambda x: np.percentile(x.dropna(), 95) if not x.dropna().empty else np.nan)
    if 'p99' in statistics_to_calc:
         agg_funcs['p99'] = pd.NamedAgg(column='value', aggfunc=lambda x: np.percentile(x.dropna(), 99) if not x.dropna().empty else np.nan)
    if 'mean' in statistics_to_calc:
         agg_funcs['mean'] = pd.NamedAgg(column='value', aggfunc='mean')
    
    # Always get sample size and traceability fields
    agg_funcs['sample_size'] = pd.NamedAgg(column='value', aggfunc='count')
    agg_funcs['first_source_row'] = pd.NamedAgg(column='source_row', aggfunc='min')
    agg_funcs['last_source_row'] = pd.NamedAgg(column='source_row', aggfunc='max')
    if 'record_date' in master_df.columns:
        agg_funcs['min_date'] = pd.NamedAgg(column='record_date', aggfunc=lambda x: x.dropna().min() if not x.dropna().empty else None)
        agg_funcs['max_date'] = pd.NamedAgg(column='record_date', aggfunc=lambda x: x.dropna().max() if not x.dropna().empty else None)
    
    # Traceability specific info per group
    # We take the first value for sheet, raw trace, raw radio, raw metric
    agg_funcs['source_sheet'] = pd.NamedAgg(column='source_sheet', aggfunc='first')
    agg_funcs['raw_trace_name'] = pd.NamedAgg(column='trace_name', aggfunc='first')
    agg_funcs['raw_network_type'] = pd.NamedAgg(column='radio_type', aggfunc='first')
    agg_funcs['raw_metric_name'] = pd.NamedAgg(column='metric_name', aggfunc='first')

    stats_df = grouped.agg(**agg_funcs).reset_index()

    # 7. Pivot for Results Report
    # We want rows to be the group_by_cols
    # Columns to be metric_name_STAT
    
    # Calculate Dataset (overall group size across all metrics)
    dataset_sizes = master_df.groupby(group_by_cols).size().reset_index(name='Dataset')
    
    values_to_pivot = [stat for stat in statistics_to_calc]
    
    try:
        results_pivot = pd.pivot_table(
            stats_df, 
            values=values_to_pivot, 
            index=group_by_cols, 
            columns=['normalized_metric'],
            aggfunc='first' # Already aggregated
        )
        
        # Flatten MultiIndex columns
        results_pivot.columns = [f"{metric}_{stat}" for stat, metric in results_pivot.columns]
        results_pivot = results_pivot.reset_index()
        
        # Merge the Dataset count
        results_pivot = pd.merge(results_pivot, dataset_sizes, on=group_by_cols, how='left')
        
        # Rename base columns to exact requested format
        rename_map = {
            'normalized_trace_name': 'Screen',
            'network_type': 'network'
        }
        results_pivot = results_pivot.rename(columns=rename_map)
        
        # Reorder columns: Screen, network, platform, Dataset, then metrics...
        # ensure those 4 are first if they exist
        first_cols = [c for c in ['Screen', 'network', 'platform', 'Dataset'] if c in results_pivot.columns]
        other_cols = [c for c in results_pivot.columns if c not in first_cols]
        results_pivot = results_pivot[first_cols + other_cols]
        
        # Sort rows so that 'screen-' data comes at the top
        if 'Screen' in results_pivot.columns:
            results_pivot['is_screen'] = results_pivot['Screen'].astype(str).str.startswith('screen-')
            results_pivot = results_pivot.sort_values(by=['is_screen', 'Screen'], ascending=[False, True])
            results_pivot = results_pivot.drop(columns=['is_screen'])
            
    except Exception as e:
         print(f"Error pivoting: {e}")
         results_pivot = stats_df # Fallback
         
    # 8. Create Traceability Dataframe (similar to stats_df but ordered nicely)
    traceability_cols = []
    
    # We will build columns matching the requested traceability sheet
    if 'section' in group_by_cols or 'section' in filters:
        traceability_cols.append('section')
    else:
        # Default if not explicitly grouped
        stats_df['section'] = 'Mixed'
        traceability_cols.append('section')

    traceability_cols.extend([
         'normalized_trace_name', 'platform', 'network_type', 
         'source_sheet', 'raw_trace_name', 'raw_network_type', 'network_type',
         'raw_metric_name', 'normalized_metric', 'sample_size'
    ])
    
    for stat in statistics_to_calc:
        if stat in stats_df.columns:
            traceability_cols.append(stat)
            
    traceability_cols.extend(['first_source_row', 'last_source_row'])
    if 'min_date' in stats_df.columns:
        traceability_cols.extend(['min_date', 'max_date'])

    # Ensure columns exist before filtering
    available_trace_cols = [c for c in traceability_cols if c in stats_df.columns]
    
    traceability_df = stats_df[available_trace_cols].copy()
    
    # Formatting
    traceability_df = traceability_df.rename(columns={
        'normalized_trace_name': 'Normalized Trace',
        'platform': 'Platform',
        'network_type': 'Normalized Network',
        'source_sheet': 'Source Sheet',
        'raw_trace_name': 'Source trace_name',
        'raw_network_type': 'Source radio_type',
        'raw_metric_name': 'Raw metric_name',
        'normalized_metric': 'Output metric',
        'sample_size': 'Sample Size',
        'first_source_row': 'First Source Row',
        'last_source_row': 'Last Source Row',
        'min_date': 'Min Date',
        'max_date': 'Max Date'
    })
    
    # 9. Create Metric Mapping documentation dataframe
    metric_map_df = pd.DataFrame(
        [(row[1], row[2], row[0], 'Yes') for row in metric_mappings.keys() for row in [(*row, metric_mappings[row])]],
        columns=['Platform', 'Output column', 'Raw metric_name', 'Available?']
    )
    
    # 10. Generate Output Excel Bytes
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if 'platform' in results_pivot.columns:
            for plat in results_pivot['platform'].unique():
                plat_df = results_pivot[results_pivot['platform'] == plat]
                # Excel sheet names can only be 31 characters
                safe_sheet_name = str(plat)[:31]
                plat_df.to_excel(writer, sheet_name=safe_sheet_name, index=False)
        else:
            results_pivot.to_excel(writer, sheet_name='Results', index=False)
            
        traceability_df.to_excel(writer, sheet_name='Traceability', index=False)
        metric_map_df.to_excel(writer, sheet_name='Metric Mapping', index=False)
        
        # Notes sheet
        notes_df = pd.DataFrame([
            ['Platform', 'Mapped exactly to the input raw data sheet name'],
            ['Network Type', 'Normalized from radio_type based on db rules'],
            ['Percentiles', f'Calculated using {", ".join(statistics_to_calc)}'],
            ['Missing values', 'Blank cells mean metric not present'],
        ], columns=['Item', 'Detail'])
        notes_df.to_excel(writer, sheet_name='Notes', index=False)
        
    output.seek(0)
    
    return output, results_pivot
