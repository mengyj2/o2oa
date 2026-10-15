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
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import {reactive, ref, onMounted} from 'vue';
import {o2, layout, component} from '@o2oa/component';
import {getConfigData, saveConfigData, deployWebResource} from '@/util/acrions';
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
  deployFail: '部署失败，请查看浏览器控制台'
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
</style>
