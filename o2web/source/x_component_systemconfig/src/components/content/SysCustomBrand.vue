<!--
  用户定制 · 品牌标识（CCIA 多租户品牌定制，2026-10-15 新增）
  ------------------------------------------------------------------
  位置：系统配置左侧导航「基础配置」与「服务配置」之间的「用户定制」分组下。
  职责：把"租户级"品牌项做成可视化维护，替代过去散落的 SQL/脚本操作。

  两条落库通道（都落在 Docker 持久卷，重建镜像不丢）：
    ① 组织信息  → 官方 config/collect.json（x_program_center.ConfigAction）
                   title  = 系统标题（登录页上部 + 浏览器标题）
                   footer = 底部申明
                   name   = 云平台账户名称（登录页底部）
                   ★ 这三项是 O2OA 官方的品牌字段，改完刷新/重登即全局生效。
    ② 品牌图形  → x_program_center.DeployAction.deployWebResource
                   部署到持久 webroot（/opt/o2server/webroot，卷 o2oa-webroot），
                   可用 Http 直接访问；供门户/登录页/桌面引用。
  ------------------------------------------------------------------
-->
<template>
  <div class="systemconfig_area" style="height:100%">
    <div class="systemconfig_title">{{ L.title }}</div>

    <div class="systemconfig_tab_area">
      <el-tabs tab-position="right">
        <!-- ============ ① 组织信息（官方 collect.json，即时生效） ============ -->
        <el-tab-pane :label="L.tabOrg" lazy>
          <div class="systemconfig_item_title">{{ L.orgSection }}</div>
          <div class="systemconfig_item_info">{{ L.orgSectionInfo }}</div>

          <BaseInput :label-style="labelStyle" :input-style="inputStyle"
                     :label="L.fTitle" v-model:value="form.title"/>
          <BaseInput :label-style="labelStyle" :input-style="inputStyle"
                     :label="L.fFooter" v-model:value="form.footer"/>
          <BaseInput :label-style="labelStyle" :input-style="inputStyle"
                     :label="L.fName" v-model:value="form.name"/>

          <div class="brand_ops">
            <button class="mainColor_bg" :disabled="saving" @click="saveOrg">
              {{ saving ? L.saving : L.save }}
            </button>
            <span class="brand_msg" :class="{brand_msg_err: !!orgError}">{{ orgMsg }}</span>
          </div>
        </el-tab-pane>

        <!-- ============ ② 品牌图形（部署到持久 webroot，可 URL 访问） ============ -->
        <el-tab-pane :label="L.tabGraph" lazy>
          <div class="systemconfig_item_title">{{ L.graphSection }}</div>
          <div class="systemconfig_item_info" v-html="L.graphSectionInfo"></div>

          <div class="brand_row" v-for="g in graphics" :key="g.key">
            <div class="brand_row_head">
              <span class="brand_row_label">{{ g.label }}</span>
              <span class="brand_row_path">{{ g.path }}/{{ g.fileName }}</span>
            </div>
            <div class="brand_row_body">
              <div class="brand_preview">
                <img v-if="g.preview" :src="g.preview" alt="" @error="onPreviewError(g)"/>
                <span v-else class="brand_preview_empty">{{ L.noImage }}</span>
              </div>
              <div class="brand_row_ops">
                <input type="file" accept="image/*" style="display:none"
                       :ref="el => setFileInput(g.key, el)" @change="(e)=>onPick(g, e)"/>
                <button @click="pickFile(g.key)">{{ L.selectFile }}</button>
                <button class="mainColor_bg" :disabled="!g.file || g.uploading"
                        @click="uploadGraphic(g)">
                  {{ g.uploading ? L.uploading : L.deploy }}
                </button>
                <div class="brand_row_hint">{{ g.hint }}</div>
                <div class="brand_msg" :class="{brand_msg_err: !!g.error}">{{ g.msg }}</div>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <!-- ============ ③ 顶栏蓝底适配（白底卡片 + 白色文字，合成 logo_topbar.png） ============ -->
        <el-tab-pane :label="L.tabTopbar" lazy>
          <div class="systemconfig_item_title">{{ L.topbarSection }}</div>
          <div class="systemconfig_item_info" v-html="L.topbarSectionInfo"></div>

          <div class="brand_switch_row">
            <span class="brand_switch_label">{{ L.topbarWhite }}</span>
            <label class="brand_switch">
              <input type="checkbox" v-model="topbar.white"/>
              <span class="brand_switch_track"><span class="brand_switch_thumb"></span></span>
            </label>
            <span class="brand_switch_tip">{{ topbar.white ? L.on : L.off }}</span>
          </div>

          <BaseInput :label-style="labelStyle" :input-style="inputStyle"
                     :label="L.topbarText" v-model:value="topbar.text" :placeholder="form.title"/>

          <div class="brand_row">
            <div class="brand_row_head">
              <span class="brand_row_label">{{ L.topbarSource }}</span>
              <span class="brand_row_path">/custom_brand/logo_topbar.png</span>
            </div>
            <div class="brand_row_body">
              <div class="brand_preview brand_preview_topbar">
                <img v-if="topbar.preview" :src="topbar.preview" alt=""/>
                <span v-else class="brand_preview_empty">{{ L.noImage }}</span>
              </div>
              <div class="brand_row_ops">
                <input type="file" accept="image/*" style="display:none"
                       ref="topbarFileInput" @change="onPickTopbarSrc"/>
                <button @click="$refs.topbarFileInput.click()">{{ L.selectFile }}</button>
                <button class="mainColor_bg" :disabled="topbar.generating"
                        @click="buildAndDeployTopbar">
                  {{ topbar.generating ? L.generating : L.buildDeploy }}
                </button>
                <div class="brand_row_hint">{{ L.topbarHint }}</div>
                <div class="brand_msg" :class="{brand_msg_err: !!topbar.error}">{{ topbar.msg }}</div>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import {reactive, ref, onMounted} from 'vue';
import {o2, layout, component} from '@o2oa/component';
import {getConfigData, saveConfigData, deployWebResource} from '@/util/acrions';
import {fetchLogoImage, fileToImage, generateTopbarWhite, passthroughBlob} from '@/util/topbarLogo';
import BaseInput from '@/components/item/BaseInput.vue';

/* 本部署为中文单语；文案内联，避免改动 108KB 的 lp 语言包（保持零侵入）。 */
const L = {
  title: '用户定制 · 品牌标识',
  tabOrg: '组织信息',
  tabGraph: '品牌图形',
  orgSection: '组织信息',
  orgSectionInfo: '以下三项是 O2OA 官方的品牌字段，落库到 config/collect.json（持久卷）。保存后刷新浏览器即可看到新名称；登录页显示的标题可能需重新打开登录页。',
  fTitle: '组织名称（系统标题）',
  fFooter: '系统页脚 / 版权',
  fName: '登录页底部名称',
  save: '保存组织信息',
  saving: '保存中…',
  graphSection: '品牌图形',
  graphSectionInfo: '图片将部署到系统的 Web 资源目录（持久卷，可通过 Http 访问）。<br/>系统 Logo 供门户/登录页/桌面引用；站点图标(favicon)用于浏览器标签页。',
  selectFile: '选择图片',
  deploy: '上传并部署',
  uploading: '部署中…',
  noImage: '（未部署）',
  deployOk: '部署成功',
  deployFail: '部署失败，请查看浏览器控制台',
  tabTopbar: '顶栏蓝底适配',
  topbarSection: '顶栏 Logo 蓝底适配',
  topbarSectionInfo: '门户顶栏为蓝底，原 Logo 中的黑字在其上几乎不可读。开启后，系统会从品牌 Logo 中切出左侧徽标、垫一张白色圆角卡片，并以<b>白色粗体</b>渲染右侧组织名称，合成 <b>logo_topbar.png</b> 供顶栏引用（顶栏已永久指向该文件）。<br/>关闭则把原 Logo 透传部署，恢复原始观感。',
  topbarWhite: '启用顶栏白底适配',
  topbarText: '顶栏白色文字（组织名称）',
  topbarSource: '顶栏 Logo 源',
  topbarHint: '未单独选图时，将从当前 /custom_brand/logo.png 合成；选中图则优先用所选图。在「品牌图形」上传新 Logo 且本开关开启时，会同步自动生成顶栏版。',
  buildDeploy: '生成并部署顶栏 Logo',
  generating: '生成中…',
  on: '已启用',
  off: '已关闭'
};

const labelStyle = {fontWeight: 'bold', fontSize: '16px', minWidth: '150px'};
const inputStyle = {width: '520px'};

const form = reactive({title: '', footer: '', name: ''});
const saving = ref(false);
const orgMsg = ref('');
const orgError = ref(false);

/** 读取官方 collect.json（有则回填，无则留空不影响保存）。 */
async function loadOrg() {
  try {
    const data = await getConfigData('collect', true);
    if (data) {
      form.title = data.title || '';
      form.footer = data.footer || '';
      form.name = data.name || '';
      // 顶栏白底适配偏好
      if (typeof data.topbarLogoWhite !== 'undefined') topbar.white = !!data.topbarLogoWhite;
      topbar.text = data.topbarLogoText || '';
    }
  } catch (e) {
    orgError.value = true;
    orgMsg.value = '读取 collect.json 失败：' + e;
  }
}

/** 保存组织信息 → collect.json（合并写，不丢其它字段如 ### 说明）。 */
async function saveOrg() {
  saving.value = true;
  orgError.value = false;
  orgMsg.value = '';
  try {
    await saveConfigData('collect', {
      title: form.title,
      footer: form.footer,
      name: form.name
    });
    orgMsg.value = '已保存到 config/collect.json。刷新页面即可看到新的组织名称。';
    component.notice('组织信息已保存', 'success');
  } catch (e) {
    orgError.value = true;
    orgMsg.value = '保存失败：' + e;
  } finally {
    saving.value = false;
  }
}

/* ---------------- 品牌图形：部署到持久 webroot ---------------- */
const fileInputs = {};
const setFileInput = (key, el) => { if (el) fileInputs[key] = el; };
const pickFile = (key) => { const el = fileInputs[key]; if (el) el.click(); };

/* ---------------- 顶栏蓝底适配 ---------------- */
const topbar = reactive({
  white: false,
  text: '',
  srcFile: null,
  preview: '',
  generating: false,
  msg: '',
  error: false
});

function onPickTopbarSrc(e) {
  const files = e.target.files;
  if (!files || !files.length) return;
  topbar.srcFile = files[0];
  topbar.msg = '';
  topbar.error = false;
  const reader = new FileReader();
  reader.onload = () => { topbar.preview = reader.result; };
  reader.readAsDataURL(topbar.srcFile);
}

/** 把合成/透传得到的 Blob 部署为 /custom_brand/logo_topbar.png */
function deployTopbarBlob(blob) {
  const fixed = new File([blob], 'logo_topbar.png', { type: 'image/png' });
  return new Promise((resolve, reject) => {
    deployWebResource({
      file: [fixed],
      overwrite: 'true',
      path: '/custom_brand',
      title: 'brand-topbar',
      version: (layout && layout.config && layout.config.version) || '1.0',
      remark: '用户定制 · 顶栏蓝底适配'
    }, resolve, reject);
  });
}

/** 生成并部署顶栏 Logo；white=生成白底卡片+白字，否则透传原图 */
async function buildAndDeployTopbar() {
  topbar.generating = true;
  topbar.msg = '';
  topbar.error = false;
  try {
    const img = topbar.srcFile ? await fileToImage(topbar.srcFile) : await fetchLogoImage();
    const blob = topbar.white
      ? await generateTopbarWhite(img, topbar.text || form.title)
      : await passthroughBlob(img);
    topbar.preview = URL.createObjectURL(blob);
    await deployTopbarBlob(blob);
    // 把偏好写入 collect.json（即时回填，避免下次读旧值）
    await saveConfigData('collect', {
      title: form.title, footer: form.footer, name: form.name,
      topbarLogoWhite: topbar.white, topbarLogoText: topbar.text
    }, true);
    topbar.msg = '已生成并部署 logo_topbar.png' + (topbar.white ? '（白底卡片 + 白色文字）' : '（透传原图）')
      + '。刷新门户即可看到顶栏变化。';
    component.notice('顶栏 Logo 已部署', 'success');
  } catch (e) {
    topbar.error = true;
    topbar.msg = '生成/部署失败：' + e;
  } finally {
    topbar.generating = false;
  }
}

const graphics = reactive([
  {
    key: 'logo',
    label: '系统 Logo',
    path: '/custom_brand',
    fileName: 'logo.png',
    hint: '供门户顶栏 / 登录页 / 桌面引用的统一 Logo。',
    file: null, preview: '', uploading: false, msg: '', error: false
  },
  {
    key: 'favicon',
    label: '站点图标（favicon）',
    path: '/custom_brand',
    fileName: 'favicon.ico',
    hint: '浏览器标签页图标；建议使用 .ico 或 32x32 的 .png。',
    file: null, preview: '', uploading: false, msg: '', error: false
  }
]);

function onPick(g, e) {
  const files = e.target.files;
  if (!files || !files.length) return;
  g.file = files[0];
  g.msg = '';
  g.error = false;
  const reader = new FileReader();
  reader.onload = () => { g.preview = reader.result; };
  reader.readAsDataURL(g.file);
}

function onPreviewError(g) { g.preview = ''; }

/** 主 Logo 上传后自动联动生成顶栏版（best-effort，失败只提示不阻断主流程） */
async function autoBuildTopbar(file) {
  try {
    const img = await fileToImage(file);
    const blob = await generateTopbarWhite(img, topbar.text || form.title);
    await deployTopbarBlob(blob);
    if (!topbar.preview) topbar.preview = URL.createObjectURL(blob);
  } catch (e) {
    console.warn('顶栏自动联动生成失败（不影响主 Logo 部署）:', e);
  }
}

/** 把选中的图片以固定文件名部署到 webroot。 */
function uploadGraphic(g) {
  if (!g.file) return;
  g.uploading = true;
  g.msg = '';
  g.error = false;
  try {
    // 统一文件名（部署接口取 File.name 作为落地名）
    const fixed = new File([g.file], g.fileName, {type: g.file.type || 'image/png'});
    deployWebResource({
      file: [fixed],
      overwrite: 'true',
      path: g.path,
      title: 'brand-' + g.key,
      version: (layout && layout.config && layout.config.version) || '1.0',
      remark: '用户定制 · 品牌标识'
    }, () => {
      g.uploading = false;
      g.msg = L.deployOk + '：' + g.path + '/' + g.fileName;
      component.notice(g.label + ' ' + L.deployOk, 'success');
      // 主 Logo 部署成功且顶栏白底适配开启 → 用同一张图自动生成顶栏版
      if (g.key === 'logo' && topbar.white && g.file) {
        autoBuildTopbar(g.file);
      }
    }, () => {
      g.uploading = false;
      g.error = true;
      g.msg = L.deployFail;
    });
  } catch (e) {
    g.uploading = false;
    g.error = true;
    g.msg = '部署异常：' + e;
  }
}

onMounted(loadOrg);
</script>

<style scoped>
.brand_ops {
  display: flex;
  align-items: center;
  padding: 20px 30px;
}
.brand_ops button,
.brand_row_ops button {
  border-radius: 100px;
  border: 0;
  padding: 6px 22px;
  cursor: pointer;
  margin-right: 14px;
}
.brand_ops button:disabled,
.brand_row_ops button:disabled {
  opacity: 0.6;
  background-color: #cccccc !important;
  color: #333333 !important;
  cursor: not-allowed;
}
.brand_msg {
  font-size: 13px;
  color: #00b516;
}
.brand_msg_err {
  color: #d9534f;
}
.brand_row {
  margin: 18px 30px;
  border: 1px solid #e7e7e7;
  border-radius: 8px;
  overflow: hidden;
}
.brand_row_head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: #f7f9fc;
}
.brand_row_label {
  font-weight: bold;
  font-size: 15px;
  color: #333;
}
.brand_row_path {
  font-size: 12px;
  color: #909399;
}
.brand_row_body {
  display: flex;
  padding: 16px;
  align-items: flex-start;
}
.brand_preview {
  width: 180px;
  height: 90px;
  border: 1px dashed #dcdfe6;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #fff;
  flex: 0 0 auto;
}
.brand_preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.brand_preview_empty {
  font-size: 12px;
  color: #c0c4cc;
}
.brand_row_ops {
  margin-left: 20px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}
.brand_row_hint {
  width: 100%;
  margin-top: 10px;
  font-size: 12px;
  color: #909399;
}

/* 顶栏蓝底适配页 */
.brand_switch_row {
  display: flex;
  align-items: center;
  padding: 16px 30px 6px;
}
.brand_switch_label {
  font-weight: bold;
  font-size: 16px;
  min-width: 150px;
}
.brand_switch {
  position: relative;
  display: inline-block;
  width: 46px;
  height: 24px;
  cursor: pointer;
}
.brand_switch input {
  position: absolute;
  opacity: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  cursor: pointer;
}
.brand_switch_track {
  position: absolute;
  inset: 0;
  background: #c0c4cc;
  border-radius: 100px;
  transition: background 0.2s;
}
.brand_switch_thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 20px;
  height: 20px;
  background: #fff;
  border-radius: 50%;
  transition: left 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.25);
}
.brand_switch input:checked + .brand_switch_track {
  background: var(--mainColor, #409eff);
}
.brand_switch input:checked + .brand_switch_track .brand_switch_thumb {
  left: 24px;
}
.brand_switch_tip {
  margin-left: 12px;
  font-size: 13px;
  color: #909399;
}
.brand_preview_topbar {
  background: rgb(46, 130, 247);
}
</style>
