package com.x.file.assemble.control.jaxrs;

import javax.servlet.annotation.WebFilter;

import com.x.base.core.project.jaxrs.CipherManagerUserJaxrsFilter;

/**
 * 企业网盘（orgdrive）鉴权过滤器。
 *
 * <p>O2OA 的 jaxrs 鉴权是按路径用 {@code @WebFilter} 注册的过滤器实现，
 * 未注册过滤器的路径会被当作匿名请求放行（实测：不带过滤器时
 * {@code effectivePerson.getDistinguishedName()} 返回 "anonymous"，写操作仍能落地）。
 *
 * <p>因此新增 jaxrs/orgdrive 路由必须同时注册本过滤器，语义与官方
 * {@link ShareJaxrsFilter} / {@link Folder2JaxrsFilter} 保持一致：
 * 要求已登录用户（CipherManagerUser），未登录一律拒绝。
 */
@WebFilter(urlPatterns = "/jaxrs/orgdrive/*", asyncSupported = true)
public class OrgDriveJaxrsFilter extends CipherManagerUserJaxrsFilter {

}
