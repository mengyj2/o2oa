package com.x.general.assemble.control.jaxrs.invoice;

import com.x.base.core.container.EntityManagerContainer;
import com.x.base.core.project.jaxrs.StandardJaxrsAction;
import com.x.base.core.project.logger.Logger;
import com.x.base.core.project.logger.LoggerFactory;
import com.x.base.core.project.tools.DateTools;
import com.x.general.assemble.control.tools.PdfElectronicInvoiceTools;
import com.x.general.assemble.control.tools.PdfRailwayInvoiceTools;
import com.x.general.assemble.control.tools.PdfRegularInvoiceTools;
import com.x.general.core.entity.Invoice;
import com.x.general.core.entity.InvoiceDetail;
import java.util.stream.Collectors;
import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.lang3.StringUtils;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.text.PDFTextStripper;

abstract class BaseAction extends StandardJaxrsAction {

    private static final Logger LOGGER = LoggerFactory.getLogger(BaseAction.class);

    protected boolean exists(EntityManagerContainer emc, String number) throws Exception {
        if(StringUtils.isNotBlank(number)){
            return emc.countEqual(Invoice.class, Invoice.number_FIELDNAME, number) > 0;
        }
        return false;
    }

    protected void extractInvoice(Invoice invoice, byte[] bytes) throws Exception {
        try {
            PDDocument doc;
            try {
                doc = Loader.loadPDF(bytes);
            } catch (Exception e) {
                // 非 PDF / 加密 PDF / 损坏文件：给出可理解的提示，而不是底层异常原文
                throw new ExceptionErrorExtract("文件不是有效的 PDF（可能已加密或损坏），无法解析：" + e.getMessage());
            }
            try {
                if (doc.getNumberOfPages() < 1) {
                    throw new ExceptionErrorExtract("该 PDF 没有任何页面，无法解析");
                }
                PDPage firstPage = doc.getPage(0);
                int pageWidth = Math.round(firstPage.getCropBox().getWidth());
                PDFTextStripper textStripper = new PDFTextStripper();
                textStripper.setSortByPosition(true);
                String fullText = textStripper.getText(doc);
                if (firstPage.getRotation() != 0) {
                    pageWidth = Math.round(firstPage.getCropBox().getHeight());
                }
                String allText = PdfRegularInvoiceTools.replace(fullText).replace("（", "(")
                        .replace("）", ")").replace("￥", "¥");
                invoice.setContent(fullText);
                LOGGER.info("{}-文件解析的发票内容:{}", invoice.getName(), allText);
                // ★ 2026-10-08 加固：把「结构解析」与「上传成败」解耦。
                //   三个解析器都是「先正则提取通用字段（号码/金额/抬头/日期）→ 再按关键词坐标法提取明细」。
                //   发票 PDF 版式千变万化（不同开票平台/税控版本），坐标法遇到未知版式可能仍抛异常；
                //   此时异常若冒泡出去，整张发票就 500 不入库（本次事故就是这个形态）。
                //   故此处把解析异常降级为「仅通用字段入库」，保证上传不失败、用户可人工补录明细。
                try {
                    if (allText.contains(PdfRailwayInvoiceTools.KEY)) {
                        LOGGER.info("解析铁路电子发票各项信息");
                        PdfRailwayInvoiceTools.getInvoice(allText, invoice);
                    } else if (allText.contains("电子发票") || allText.contains("电⼦发票")) {
                        LOGGER.info("解析电子发票各项信息");
                        PdfElectronicInvoiceTools.getFullElectronicInvoice(allText, pageWidth, doc,
                                firstPage, invoice);
                    } else {
                        LOGGER.info("解析包含密码区发票各项信息");
                        PdfRegularInvoiceTools.getRegularInvoice(allText, pageWidth, doc, firstPage,
                                invoice);
                    }
                } catch (Exception parseException) {
                    LOGGER.warn("[INVOICE-DEGRADED] 发票结构解析失败，已降级为「仅通用字段入库」，明细需人工核对：{}",
                            parseException.getMessage());
                    LOGGER.error(parseException);
                }
                if (StringUtils.isNotBlank(invoice.getDate())) {
                    try {
                        invoice.setInvoiceDate(DateTools.parse(invoice.getDate(), "yyyy年MM月dd日"));
                    } catch (Exception e) {
                        LOGGER.warn("发票日期：{}，转换错误：{}", invoice.getDate(), e.getMessage());
                    }
                }
                if (CollectionUtils.isNotEmpty(invoice.getProperties().getDetailList())) {
                    invoice.setDetail(
                            invoice.getProperties().getDetailList().stream()
                                    .map(InvoiceDetail::getName).distinct()
                                    .collect(Collectors.joining(",")));
                }
                // ★ 底线校验：号码/代码/金额/价税合计 全空 ⇒ 基本可判定「没能识别出这是一张发票」，
                //   典型是纯图片扫描件（无文本层）或根本不是发票。此时明确报错，
                //   既不静默入库空发票污染「发票池」，也把处理建议直接告诉用户。
                if (StringUtils.isBlank(invoice.getNumber()) && StringUtils.isBlank(invoice.getCode())
                        && null == invoice.getAmount() && null == invoice.getTotalAmount()) {
                    throw new ExceptionErrorExtract("未能从该 PDF 识别出发票要素（发票号码、代码、金额均为空）"
                            + "，请确认这是可选中文字的电子发票 PDF；若为扫描件或照片，请改用图片方式上传由 OCR 识别");
                }
            } finally {
                try {
                    doc.close();
                } catch (Exception ignore) {
                    // 解析器可能已关闭文档，重复关闭忽略即可
                }
            }
        } catch (Exception e) {
            LOGGER.error(e);
            if (e instanceof ExceptionErrorExtract) {
                throw e;
            }
            throw new ExceptionErrorExtract(e.getMessage());
        }
    }
}
