import re

with open('plugins/admin.py', 'r') as f:
    content = f.read()

replacements = {
    r'data\.startswith\("admin_myfiles_edit_limits_"\)': r'data.startswith("adm_myf_ed_")',
    r'data\.replace\("admin_myfiles_edit_limits_", ""\)': r'data.replace("adm_myf_ed_", "")',
    r'data\.startswith\("admin_edit_plan_"\)': r'data.startswith("adm_pln_ed_")',
    r'data\.replace\("admin_edit_plan_", ""\)': r'data.replace("adm_pln_ed_", "")',
    r'data\.startswith\("admin_premium_"\)': r'(data.startswith("adm_pln_p_") or data.startswith("adm_pln_feat_") or data.startswith("adm_pln_pf_") or data.startswith("adm_pln_pm_") or data.startswith("adm_pln_pt_"))',
    r'data\.startswith\("prompt_premium_"\)': r'data.startswith("adm_pln_p_")',
    r'data\.startswith\("prompt_trial_"\)': r'data.startswith("adm_pln_p_trd")',
    r'data\.startswith\("admin_trial_"\)': r'data.startswith("adm_pln_tr_tgl")',
    r'data\.startswith\("admin_pay_toggle_"\)': r'data.startswith("adm_pay_tgl_")',
    r'data\.replace\("admin_pay_toggle_", ""\)': r'data.replace("adm_pay_tgl_", "")',
    r'data\.startswith\("admin_pay_approve_"\)': r'data.startswith("adm_pay_ap_")',
    r'data\.replace\("admin_pay_approve_", ""\)': r'data.replace("adm_pay_ap_", "")',
    r'data\.startswith\("admin_pay_reject_"\)': r'data.startswith("adm_pay_rj_")',
    r'data\.replace\("admin_pay_reject_", ""\)': r'data.replace("adm_pay_rj_", "")',
    r'data\.startswith\("admin_public_"\)': r'data.startswith("adm_pub_")',
    r'data\.startswith\("admin_daily_"\)': r'(data.startswith("adm_pln_free_eg") or data.startswith("adm_pln_free_fl"))',
    r'data\.startswith\("admin_force_sub_"\)': r'data.startswith("adm_fs_")',
    r'data\.startswith\("admin_fs_"\)': r'data.startswith("adm_fs_")',
    r'data\.startswith\("admin_fs_rem_ch_"\)': r'data.startswith("adm_fs_rmc_")',
    r'data\.replace\("admin_fs_rem_ch_", ""\)': r'data.replace("adm_fs_rmc_", "")',
    r'data\.startswith\("admin_set_sep_"\)': r'data.startswith("adm_tpl_s_")',
    r'data\.replace\("admin_set_sep_", ""\)': r'data.replace("adm_tpl_s_", "")',
    r'data\.startswith\("admin_set_lang_"\)': r'data.startswith("adm_gen_ln_")',
    r'data\.replace\("admin_set_lang_", ""\)': r'data.replace("adm_gen_ln_", "")',
    r'data\.split\("admin_set_sep_"\)\[1\]': r'data.split("adm_tpl_s_")[1]',
}

for k, v in replacements.items():
    content = re.sub(k, v, content)

with open('plugins/admin.py', 'w') as f:
    f.write(content)
