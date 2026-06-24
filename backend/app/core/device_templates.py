"""默认设备配置模板。

为各主流厂商路由器提供 RPKI-RTR 客户端、ROV 策略、回滚与风险提示
四类默认配置模板。模板内容使用 ``{{ var }}`` 形式的变量占位符，
生成时由 :mod:`app.services.device_config_service` 填充。

支持厂商：
- Cisco IOS XE / IOS XR
- Juniper JunOS
- Huawei VRP
- H3C
- Arista EOS
- Nokia SR OS
- FRRouting
- BIRD
- OpenBGPD
"""

from __future__ import annotations

from typing import Any


# ──────────────────────────────────────────────
# 厂商元数据
# ──────────────────────────────────────────────


VENDOR_NAMES: dict[str, str] = {
    "cisco_ios_xe": "Cisco IOS XE",
    "cisco_ios_xr": "Cisco IOS XR",
    "juniper_junos": "Juniper JunOS",
    "huawei_vrp": "Huawei VRP",
    "h3c": "H3C Comware",
    "arista_eos": "Arista EOS",
    "nokia_sros": "Nokia SR OS",
    "frr": "FRRouting",
    "bird": "BIRD",
    "openbgpd": "OpenBGPD",
}


# 通用变量定义（所有厂商共享）
COMMON_VARIABLES: dict[str, dict[str, Any]] = {
    "asn": {
        "description": "本地 AS 号",
        "required": True,
        "example": "64512",
    },
    "rtr_server": {
        "description": "RTR 服务器地址",
        "required": True,
        "example": "10.0.0.1",
    },
    "rtr_port": {
        "description": "RTR 服务器端口",
        "required": True,
        "default": 8282,
        "example": "8282",
    },
    "refresh_interval": {
        "description": "刷新间隔（秒）",
        "required": False,
        "default": 3600,
    },
    "retry_interval": {
        "description": "重试间隔（秒）",
        "required": False,
        "default": 600,
    },
    "expire_interval": {
        "description": "过期时间（秒）",
        "required": False,
        "default": 7200,
    },
    "router_id": {
        "description": "BGP Router ID",
        "required": False,
        "example": "10.0.0.1",
    },
    "policy": {
        "description": "ROV 策略：drop_invalid/de_preference_invalid/monitor_only",
        "required": False,
        "default": "drop_invalid",
        "example": "drop_invalid",
    },
    "localpref_valid": {
        "description": "Valid 路由的 localpreference 值",
        "required": False,
        "default": 200,
    },
    "localpref_invalid": {
        "description": "Invalid 路由的 localpreference 值（降级模式使用）",
        "required": False,
        "default": 50,
    },
    "localpref_not_found": {
        "description": "NotFound 路由的 localpreference 值",
        "required": False,
        "default": 100,
    },
}


# ──────────────────────────────────────────────
# ROV 策略定义
# ──────────────────────────────────────────────


# 支持的 ROV 策略
POLICY_NAMES: dict[str, str] = {
    "drop_invalid": "drop-invalid（拒绝 Invalid 路由）",
    "de_preference_invalid": "de-preference-invalid（降低 Invalid 路由优先级）",
    "monitor_only": "monitor-only（仅监控，不干预路由）",
}


# ──────────────────────────────────────────────
# 默认模板内容
# ──────────────────────────────────────────────


# Cisco IOS XE
CISCO_IOS_XE_TEMPLATES: dict[str, str] = {
    "rtr_client": """! Cisco IOS XE RPKI-RTR 客户端配置
! 生成时间: {{ generated_at }}
hostname {{ hostname | default "rpki-router" }}
!
! 配置 RPKI 缓存服务器
router bgp {{ asn }}
 bgp router-id {{ router_id | default "10.0.0.1" }}
 bgp log-neighbor-changes
 !
 address-family ipv4
  bgp rpki server tcp {{ rtr_server }} port {{ rtr_port }} refresh {{ refresh_interval | default 3600 }}
  bgp rpki bestpath use-policies
 exit-address-family
 !
 address-family ipv6
  bgp rpki server tcp {{ rtr_server }} port {{ rtr_port }} refresh {{ refresh_interval | default 3600 }}
 exit-address-family
!
""",
    "rov_policy": """! Cisco IOS XE RPKI ROV 策略配置
router bgp {{ asn }}
 address-family ipv4
  bgp rpki bestpath invalid reject
  ! 也可使用 de-preference 模式：bgp rpki bestpath invalid de-preference
 exit-address-family
!
""",
    "rollback": """! Cisco IOS XE RPKI 回滚配置
! 紧急情况下撤销 ROV 策略
no bgp rpki bestpath invalid reject
! 或完全关闭 RTR 会话
router bgp {{ asn }}
 address-family ipv4
  no bgp rpki server tcp {{ rtr_server }} port {{ rtr_port }}
 exit-address-family
!
""",
    "risk_notice": """! 风险提示：RPKI 部署注意事项
! 1. 部署 ROV 前请确认 RTR 会话已建立（show bgp rpki servers）
! 2. 建议先使用 de-preference 模式观察一段时间再切换为 reject
! 3. RTR 服务器故障时，已缓存的 VRP 在 expire_interval 内仍有效
! 4. 当前 AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
! 5. 如发生误拒，可使用 rollback 模板快速恢复
""",
}

# Cisco IOS XR
CISCO_IOS_XR_TEMPLATES: dict[str, str] = {
    "rtr_client": """! Cisco IOS XR RPKI-RTR 客户端配置
! 生成时间: {{ generated_at }}
hostname {{ hostname | default "rpki-router" }}
!
router bgp {{ asn }}
 bgp router-id {{ router_id | default "10.0.0.1" }}
 bgp cluster-id 1
 !
 rpki server {{ rtr_server }}
  transport tcp port {{ rtr_port }}
  refresh-time {{ refresh_interval | default 3600 }}
  response-time 60
  purge-time {{ expire_interval | default 7200 }}
 !
!
""",
    "rov_policy": """! Cisco IOS XR RPKI ROV 策略配置
router bgp {{ asn }}
 address-family ipv4 unicast
  bgp bestpath origin-as use rpki invalid-as reject
 exit
!
""",
    "rollback": """! Cisco IOS XR RPKI 回滚配置
router bgp {{ asn }}
 no rpki server {{ rtr_server }}
!
""",
    "risk_notice": """! 风险提示：IOS XR RPKI 部署
! 1. IOS XR 默认对 invalid 路由 reject，请先观察 rpki validation 状态
! 2. 使用 show bgp rpki table 查看本地 VRP 缓存
! 3. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}

# Juniper JunOS
JUNIPER_JUNOS_TEMPLATES: dict[str, str] = {
    "rtr_client": """# Juniper JunOS RPKI-RTR 客户端配置
# 生成时间: {{ generated_at }}
routing-options {
    router-id {{ router_id | default "10.0.0.1" }};
    autonomous-system {{ asn }};
    validation {
        group rpki-validator {
            session {{ rtr_server }} {
                port {{ rtr_port }};
                refresh-time {{ refresh_interval | default 3600 }};
                hold-time {{ expire_interval | default 7200 }};
                record-lifetime {{ expire_interval | default 7200 }};
            }
        }
    }
}
protocols {
    bgp {
        group rpki-peers {
            type external;
            family inet {
                unicast;
            }
        }
    }
}
""",
    "rov_policy": """# Juniper JunOS RPKI ROV 策略配置
policy-options {
    policy-statement rpki-valid {
        term valid {
            from protocol bgp;
            then validation-state valid;
            then accept;
        }
    }
    policy-statement rpki-invalid {
        term invalid {
            from protocol bgp;
            then validation-state invalid;
            then reject;
        }
    }
}
protocols {
    bgp {
        group rpki-peers {
            import rpki-invalid;
        }
    }
}
""",
    "rollback": """# Juniper JunOS RPKI 回滚配置
routing-options {
    no-validation;
}
""",
    "risk_notice": """# 风险提示：JunOS RPKI 部署
# 1. 使用 show validation statistics 查看 VRP 缓存状态
# 2. 建议先 import rpki-invalid 策略，再启用 reject
# 3. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}

# Huawei VRP
HUAWEI_VRP_TEMPLATES: dict[str, str] = {
    "rtr_client": """! Huawei VRP RPKI-RTR 客户端配置
! 生成时间: {{ generated_at }}
sysname {{ hostname | default "rpki-router" }}
#
bgp {{ asn }}
 router-id {{ router_id | default "10.0.0.1" }}
 #
 rpki-server {{ rtr_server }} port {{ rtr_port }}
  refresh-time {{ refresh_interval | default 3600 }} seconds
  purge-time {{ expire_interval | default 7200 }} seconds
 #
 #
 peer 10.0.0.2 as-number 64513
 #
 ipv4-family unicast
  peer 10.0.0.2 enable
  peer 10.0.0.2 route-policy rpki-policy import
 #
#
""",
    "rov_policy": """! Huawei VRP RPKI ROV 策略配置
route-policy rpki-policy permit node 10
 if-match rpki invalid
 apply preference 200
route-policy rpki-policy permit node 20
 if-match rpki valid
 apply preference 100
#
bgp {{ asn }}
 ipv4-family unicast
  peer 10.0.0.2 route-policy rpki-policy import
 #
#
""",
    "rollback": """! Huawei VRP RPKI 回滚配置
bgp {{ asn }}
 undo rpki-server {{ rtr_server }} port {{ rtr_port }}
 #
#
""",
    "risk_notice": """! 风险提示：Huawei VRP RPKI 部署
! 1. 使用 display bgp rpki table 查看 VRP 缓存
! 2. 建议先使用 preference 降级模式，再启用 reject
! 3. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}

# H3C
H3C_TEMPLATES: dict[str, str] = {
    "rtr_client": """! H3C Comware RPKI-RTR 客户端配置
! 生成时间: {{ generated_at }}
sysname {{ hostname | default "rpki-router" }}
#
bgp {{ asn }}
 router-id {{ router_id | default "10.0.0.1" }}
 #
 rpki server {{ rtr_server }} port {{ rtr_port }}
  refresh-time {{ refresh_interval | default 3600 }}
  purge-time {{ expire_interval | default 7200 }}
 #
#
""",
    "rov_policy": """! H3C Comware RPKI ROV 策略配置
bgp {{ asn }}
 address-family ipv4
  rpki bestpath invalid reject
 #
#
""",
    "rollback": """! H3C Comware RPKI 回滚配置
bgp {{ asn }}
 undo rpki server {{ rtr_server }} port {{ rtr_port }}
#
""",
    "risk_notice": """! 风险提示：H3C RPKI 部署
! 1. 使用 display bgp rpki server 查看 RTR 会话状态
! 2. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}

# Arista EOS
ARISTA_EOS_TEMPLATES: dict[str, str] = {
    "rtr_client": """! Arista EOS RPKI-RTR 客户端配置
! 生成时间: {{ generated_at }}
hostname {{ hostname | default "rpki-router" }}
!
router bgp {{ asn }}
   router-id {{ router_id | default "10.0.0.1" }}
   rpki server {{ rtr_server }}
      port {{ rtr_port }}
      refresh-time {{ refresh_interval | default 3600 }}
      expire-time {{ expire_interval | default 7200 }}
!
""",
    "rov_policy": """! Arista EOS RPKI ROV 策略配置
router bgp {{ asn }}
   bgp bestpath rpki-invalid reject
   ! 或使用降级模式：bgp bestpath rpki-invalid lower-priority
!
""",
    "rollback": """! Arista EOS RPKI 回滚配置
router bgp {{ asn }}
   no rpki server {{ rtr_server }}
!
""",
    "risk_notice": """! 风险提示：Arista EOS RPKI 部署
! 1. 使用 show bgp rpki 查看会话与 VRP 状态
! 2. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}

# Nokia SR OS
NOKIA_SROS_TEMPLATES: dict[str, str] = {
    "rtr_client": """# Nokia SR OS RPKI-RTR 客户端配置
# 生成时间: {{ generated_at }}
configure {
    router "Base" {
        autonomous-system {{ asn }}
        router-id {{ router_id | default "10.0.0.1" }}
        bgp {
            rpki {
                server "{{ rtr_server }}" {
                    port {{ rtr_port }}
                    refresh-time {{ refresh_interval | default 3600 }}
                    purge-time {{ expire_interval | default 7200 }}
                }
            }
        }
    }
}
""",
    "rov_policy": """# Nokia SR OS RPKI ROV 策略配置
configure {
    policy-options {
        policy-statement "rpki-invalid-reject" {
            entry 10 {
                from {
                    validation-state invalid
                }
                action {
                    action-type reject
                }
            }
        }
    }
    router "Base" {
        bgp {
            import "rpki-invalid-reject"
        }
    }
}
""",
    "rollback": """# Nokia SR OS RPKI 回滚配置
configure {
    router "Base" {
        bgp {
            no rpki
        }
    }
}
""",
    "risk_notice": """# 风险提示：Nokia SR OS RPKI 部署
# 1. 使用 show router bgp rpki 查看会话状态
# 2. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}

# FRRouting
FRR_TEMPLATES: dict[str, str] = {
    "rtr_client": """! FRRouting RPKI-RTR 客户端配置
! 生成时间: {{ generated_at }}
frr version 8.5
frr defaults traditional
hostname {{ hostname | default "rpki-router" }}
!
router bgp {{ asn }}
 bgp router-id {{ router_id | default "10.0.0.1" }}
 no bgp ebgp-requires-policy
 !
 rpki server {{ rtr_server }} port {{ rtr_port }}
  refresh-time {{ refresh_interval | default 3600 }}
  retry-time {{ retry_interval | default 600 }}
  expire-time {{ expire_interval | default 7200 }}
 !
!
""",
    "rov_policy": """! FRRouting RPKI ROV 策略配置
router bgp {{ asn }}
 bgp rpki bestpath use-policies
 bgp rpki bestpath invalid reject
 ! 或使用降级模式：bgp rpki bestpath invalid de-preference
!
""",
    "rollback": """! FRRouting RPKI 回滚配置
router bgp {{ asn }}
 no rpki server {{ rtr_server }} port {{ rtr_port }}
 no bgp rpki bestpath invalid reject
!
""",
    "risk_notice": """! 风险提示：FRRouting RPKI 部署
! 1. 使用 show bgp rpki servers 查看 RTR 会话
! 2. 使用 show bgp rpki table 查看 VRP 缓存
! 3. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}

# BIRD
BIRD_TEMPLATES: dict[str, str] = {
    "rtr_client": """# BIRD RPKI-RTR 客户端配置
# 生成时间: {{ generated_at }}
router id {{ router_id | default "10.0.0.1" }};

protocol rpki rpki_cache_1 {
    remote {{ rtr_server }} port {{ rtr_port }};
    retry keep {{ retry_interval | default 600 }};
    refresh keep {{ refresh_interval | default 3600 }};
    expire keep {{ expire_interval | default 7200 }};
}

protocol bgp bgp_uplink_1 {
    local {{ asn }} as {{ asn }};
    neighbor 10.0.0.2 as 64513;
    import filter {
        if roa_check(rpki_cache_1, net, bgp_path.last) = ROUTE_INVALID then
            reject;
        accept;
    };
    export all;
}
""",
    "rov_policy": """# BIRD RPKI ROV 策略配置
filter rpki_filter {
    if roa_check(rpki_cache_1, net, bgp_path.last) = ROUTE_INVALID then
        reject;
    if roa_check(rpki_cache_1, net, bgp_path.last) = ROUTE_UNKNOWN then
        accept;  # NotFound 路由放行
    accept;  # Valid 路由放行
}
""",
    "rollback": """# BIRD RPKI 回滚配置
protocol bgp bgp_uplink_1 {
    import all;  # 撤销 ROV 过滤
    export all;
}
""",
    "risk_notice": """# 风险提示：BIRD RPKI 部署
# 1. 使用 birdc show protocols 查看 RTR 会话状态
# 2. 使用 birdc show route protocol rpki_cache_1 查看 VRP
# 3. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}

# OpenBGPD
OPENBGPD_TEMPLATES: dict[str, str] = {
    "rtr_client": """# OpenBGPD RPKI-RTR 客户端配置
# 生成时间: {{ generated_at }}
AS {{ asn }}
router-id {{ router_id | default "10.0.0.1" }}
listen on 0.0.0.0

# RPKI RTR 缓存服务器
rtr {{ rtr_server }} {{ rtr_port }}

# BGP 邻居
neighbor 10.0.0.2 {
    remote-as 64513
    descr uplink_1
}

# 默认对 invalid 路由 reject
deny from any rpki invalid
allow from any
allow to any
""",
    "rov_policy": """# OpenBGPD RPKI ROV 策略配置
# 拒绝 RPKI invalid 路由
deny from any rpki invalid

# 对 valid 与 not-found 路由放行
allow from any rpki valid
allow from any rpki not-found
""",
    "rollback": """# OpenBGPD RPKI 回滚配置
# 撤销 ROV 策略
match from any set { localpref 100 }
# 完全关闭 RTR 会话
no rtr {{ rtr_server }} {{ rtr_port }}
""",
    "risk_notice": """# 风险提示：OpenBGPD RPKI 部署
# 1. 使用 bgpctl show rtr 查看 RTR 会话
# 2. 使用 bgpctl show rib validated 查看 VRP
# 3. AS={{ asn }}, RTR={{ rtr_server }}:{{ rtr_port }}
""",
}


# ──────────────────────────────────────────────
# 模板聚合
# ──────────────────────────────────────────────


DEFAULT_TEMPLATES: dict[str, dict[str, str]] = {
    "cisco_ios_xe": CISCO_IOS_XE_TEMPLATES,
    "cisco_ios_xr": CISCO_IOS_XR_TEMPLATES,
    "juniper_junos": JUNIPER_JUNOS_TEMPLATES,
    "huawei_vrp": HUAWEI_VRP_TEMPLATES,
    "h3c": H3C_TEMPLATES,
    "arista_eos": ARISTA_EOS_TEMPLATES,
    "nokia_sros": NOKIA_SROS_TEMPLATES,
    "frr": FRR_TEMPLATES,
    "bird": BIRD_TEMPLATES,
    "openbgpd": OPENBGPD_TEMPLATES,
}


# ──────────────────────────────────────────────
# 策略专用 ROV 模板
# ──────────────────────────────────────────────
#
# 为每个厂商提供三种 ROV 策略的专用模板：
# - drop_invalid：拒绝 Invalid 路由，Valid/NotFound 放行
# - de_preference_invalid：降低 Invalid 路由优先级，均放行
# - monitor_only：仅启用 RPKI 验证，不干预路由
#
# 每个模板均包含 Valid/Invalid/NotFound 匹配规则与风险提示。


POLICY_TEMPLATES: dict[str, dict[str, str]] = {
    # ── Cisco IOS XE ──
    "cisco_ios_xe": {
        "drop_invalid": """! Cisco IOS XE ROV 策略：drop-invalid
! 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
! 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
router bgp {{ asn }}
 address-family ipv4
  ! 启用 RPKI 最佳路径策略
  bgp rpki bestpath use-policies
  ! 拒绝 Invalid 路由（drop-invalid）
  bgp rpki bestpath invalid reject
  ! Valid 路由：正常接受（默认行为）
  ! NotFound 路由：正常接受（默认行为）
 exit-address-family
 !
 address-family ipv6
  bgp rpki bestpath use-policies
  bgp rpki bestpath invalid reject
 exit-address-family
!
! 验证命令：
!   show bgp rpki servers        - 查看 RTR 会话
!   show bgp rpki table          - 查看 VRP 缓存
!   show bgp ipv4 unicast rpki   - 查看路由验证状态
""",
        "de_preference_invalid": """! Cisco IOS XE ROV 策略：de-preference-invalid
! 策略说明：降低 Invalid 路由优先级，所有路由均放行
! 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
router bgp {{ asn }}
 address-family ipv4
  bgp rpki bestpath use-policies
  ! 降低 Invalid 路由优先级（de-preference-invalid）
  bgp rpki bestpath invalid de-preference
  ! Valid 路由：正常接受（默认行为）
  ! NotFound 路由：正常接受（默认行为）
 exit-address-family
 !
 address-family ipv6
  bgp rpki bestpath use-policies
  bgp rpki bestpath invalid de-preference
 exit-address-family
!
! 验证命令：
!   show bgp rpki servers        - 查看 RTR 会话
!   show bgp ipv4 unicast rpki   - 查看路由验证状态
""",
        "monitor_only": """! Cisco IOS XE ROV 策略：monitor-only
! 策略说明：仅启用 RPKI 验证，不干预路由选择
! 风险提示：所有路由均放行，仅用于监控与统计
router bgp {{ asn }}
 address-family ipv4
  ! 启用 RPKI 最佳路径策略（仅监控）
  bgp rpki bestpath use-policies
  ! 不配置 invalid reject/de-preference，仅记录验证状态
  ! Valid 路由：正常接受
  ! Invalid 路由：正常接受（仅监控）
  ! NotFound 路由：正常接受
 exit-address-family
 !
 address-family ipv6
  bgp rpki bestpath use-policies
 exit-address-family
!
! 验证命令：
!   show bgp rpki servers        - 查看 RTR 会话
!   show bgp ipv4 unicast rpki   - 查看路由验证状态（仅监控）
""",
    },
    # ── Cisco IOS XR ──
    "cisco_ios_xr": {
        "drop_invalid": """! Cisco IOS XR ROV 策略：drop-invalid
! 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
! 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
router bgp {{ asn }}
 address-family ipv4 unicast
  ! 拒绝 Invalid 路由（drop-invalid）
  bgp bestpath origin-as use rpki invalid-as reject
  ! Valid 路由：正常接受（默认行为）
  ! NotFound 路由：正常接受（默认行为）
 exit
 !
 address-family ipv6 unicast
  bgp bestpath origin-as use rpki invalid-as reject
 exit
!
! 验证命令：
!   show bgp rpki table           - 查看 VRP 缓存
!   show bgp ipv4 unicast rpki    - 查看路由验证状态
""",
        "de_preference_invalid": """! Cisco IOS XR ROV 策略：de-preference-invalid
! 策略说明：降低 Invalid 路由优先级，所有路由均放行
! 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
route-policy rpki-de-preference
  if rpki-origin-as-valid then
    set local-preference {{ localpref_valid }}
  elseif rpki-origin-as-invalid then
    set local-preference {{ localpref_invalid }}
  else
    set local-preference {{ localpref_not_found }}
  endif
end-policy
!
router bgp {{ asn }}
 address-family ipv4 unicast
  ! 降低 Invalid 路由优先级（de-preference-invalid）
  bgp bestpath origin-as use rpki
  ! Valid 路由：local-preference {{ localpref_valid }}
  ! Invalid 路由：local-preference {{ localpref_invalid }}
  ! NotFound 路由：local-preference {{ localpref_not_found }}
 exit
!
! 验证命令：
!   show bgp rpki table           - 查看 VRP 缓存
""",
        "monitor_only": """! Cisco IOS XR ROV 策略：monitor-only
! 策略说明：仅启用 RPKI 验证，不干预路由选择
! 风险提示：所有路由均放行，仅用于监控与统计
router bgp {{ asn }}
 address-family ipv4 unicast
  ! 启用 RPKI 验证（仅监控，不 reject）
  bgp bestpath origin-as use rpki
  ! Valid 路由：正常接受
  ! Invalid 路由：正常接受（仅监控）
  ! NotFound 路由：正常接受
 exit
!
! 验证命令：
!   show bgp rpki table           - 查看 VRP 缓存
!   show bgp ipv4 unicast rpki    - 查看路由验证状态（仅监控）
""",
    },
    # ── Juniper JunOS ──
    "juniper_junos": {
        "drop_invalid": """# Juniper JunOS ROV 策略：drop-invalid
# 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
# 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
policy-options {
    policy-statement rpki-rov {
        term valid {
            from protocol bgp;
            from validation-state valid;
            then accept;
        }
        term not-found {
            from protocol bgp;
            from validation-state unknown;
            then accept;
        }
        term invalid {
            from protocol bgp;
            from validation-state invalid;
            then reject;
        }
    }
}
protocols {
    bgp {
        group rpki-peers {
            import rpki-rov;
        }
    }
}
# 验证命令：
#   show validation statistics     - 查看 VRP 缓存状态
#   show route validation-state    - 查看路由验证状态
""",
        "de_preference_invalid": """# Juniper JunOS ROV 策略：de-preference-invalid
# 策略说明：降低 Invalid 路由优先级，所有路由均放行
# 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
policy-options {
    policy-statement rpki-rov-depreference {
        term valid {
            from protocol bgp;
            from validation-state valid;
            then {
                local-preference {{ localpref_valid }};
                accept;
            }
        }
        term not-found {
            from protocol bgp;
            from validation-state unknown;
            then {
                local-preference {{ localpref_not_found }};
                accept;
            }
        }
        term invalid {
            from protocol bgp;
            from validation-state invalid;
            then {
                local-preference {{ localpref_invalid }};
                accept;
            }
        }
    }
}
protocols {
    bgp {
        group rpki-peers {
            import rpki-rov-depreference;
        }
    }
}
# 验证命令：
#   show validation statistics     - 查看 VRP 缓存状态
""",
        "monitor_only": """# Juniper JunOS ROV 策略：monitor-only
# 策略说明：仅启用 RPKI 验证，不干预路由选择
# 风险提示：所有路由均放行，仅用于监控与统计
routing-options {
    validation {
        group rpki-validator {
            session {{ rtr_server }} {
                port {{ rtr_port }};
                refresh-time {{ refresh_interval | default 3600 }};
                hold-time {{ expire_interval | default 7200 }};
            }
        }
    }
}
# 不配置 import 策略，所有路由均接受
# Valid 路由：正常接受
# Invalid 路由：正常接受（仅监控）
# NotFound 路由：正常接受
# 验证命令：
#   show validation statistics     - 查看 VRP 缓存状态
#   show route validation-state    - 查看路由验证状态（仅监控）
""",
    },
    # ── Huawei VRP ──
    "huawei_vrp": {
        "drop_invalid": """! Huawei VRP ROV 策略：drop-invalid
! 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
! 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
route-policy rpki-drop-invalid deny node 10
 if-match rpki invalid
route-policy rpki-drop-invalid permit node 20
#
bgp {{ asn }}
 ipv4-family unicast
  peer 10.0.0.2 route-policy rpki-drop-invalid import
 #
#
! Valid 路由：正常接受（permit node 20）
! Invalid 路由：拒绝（deny node 10）
! NotFound 路由：正常接受（permit node 20）
! 验证命令：
!   display bgp rpki table        - 查看 VRP 缓存
!   display bgp routing-table     - 查看路由验证状态
""",
        "de_preference_invalid": """! Huawei VRP ROV 策略：de-preference-invalid
! 策略说明：降低 Invalid 路由优先级，所有路由均放行
! 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
route-policy rpki-depreference permit node 10
 if-match rpki invalid
 apply preference {{ localpref_invalid }}
route-policy rpki-depreference permit node 20
 if-match rpki valid
 apply preference {{ localpref_valid }}
route-policy rpki-depreference permit node 30
 apply preference {{ localpref_not_found }}
#
bgp {{ asn }}
 ipv4-family unicast
  peer 10.0.0.2 route-policy rpki-depreference import
 #
#
! Valid 路由：preference {{ localpref_valid }}
! Invalid 路由：preference {{ localpref_invalid }}
! NotFound 路由：preference {{ localpref_not_found }}
! 验证命令：
!   display bgp rpki table        - 查看 VRP 缓存
""",
        "monitor_only": """! Huawei VRP ROV 策略：monitor-only
! 策略说明：仅启用 RPKI 验证，不干预路由选择
! 风险提示：所有路由均放行，仅用于监控与统计
bgp {{ asn }}
 ipv4-family unicast
  ! 不应用 route-policy，所有路由均接受
  ! Valid 路由：正常接受
  ! Invalid 路由：正常接受（仅监控）
  ! NotFound 路由：正常接受
 #
#
! 验证命令：
!   display bgp rpki table        - 查看 VRP 缓存
!   display bgp routing-table     - 查看路由验证状态（仅监控）
""",
    },
    # ── H3C ──
    "h3c": {
        "drop_invalid": """! H3C Comware ROV 策略：drop-invalid
! 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
! 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
bgp {{ asn }}
 address-family ipv4
  ! 拒绝 Invalid 路由（drop-invalid）
  rpki bestpath invalid reject
  ! Valid 路由：正常接受（默认行为）
  ! NotFound 路由：正常接受（默认行为）
 #
 address-family ipv6
  rpki bestpath invalid reject
 #
#
! 验证命令：
!   display bgp rpki server       - 查看 RTR 会话状态
!   display bgp routing-table     - 查看路由验证状态
""",
        "de_preference_invalid": """! H3C Comware ROV 策略：de-preference-invalid
! 策略说明：降低 Invalid 路由优先级，所有路由均放行
! 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
bgp {{ asn }}
 address-family ipv4
  ! 降低 Invalid 路由优先级（de-preference-invalid）
  rpki bestpath invalid de-preference
  ! Valid 路由：正常接受（默认行为）
  ! NotFound 路由：正常接受（默认行为）
 #
#
! 验证命令：
!   display bgp rpki server       - 查看 RTR 会话状态
""",
        "monitor_only": """! H3C Comware ROV 策略：monitor-only
! 策略说明：仅启用 RPKI 验证，不干预路由选择
! 风险提示：所有路由均放行，仅用于监控与统计
bgp {{ asn }}
 address-family ipv4
  ! 启用 RPKI 验证（仅监控，不 reject）
  rpki bestpath use-policies
  ! Valid 路由：正常接受
  ! Invalid 路由：正常接受（仅监控）
  ! NotFound 路由：正常接受
 #
#
! 验证命令：
!   display bgp rpki server       - 查看 RTR 会话状态
!   display bgp routing-table     - 查看路由验证状态（仅监控）
""",
    },
    # ── Arista EOS ──
    "arista_eos": {
        "drop_invalid": """! Arista EOS ROV 策略：drop-invalid
! 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
! 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
router bgp {{ asn }}
   ! 拒绝 Invalid 路由（drop-invalid）
   bgp bestpath rpki-invalid reject
   ! Valid 路由：正常接受（默认行为）
   ! NotFound 路由：正常接受（默认行为）
!
! 验证命令：
!   show bgp rpki                 - 查看会话与 VRP 状态
!   show bgp ipv4 unicast rpki    - 查看路由验证状态
""",
        "de_preference_invalid": """! Arista EOS ROV 策略：de-preference-invalid
! 策略说明：降低 Invalid 路由优先级，所有路由均放行
! 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
router bgp {{ asn }}
   ! 降低 Invalid 路由优先级（de-preference-invalid）
   bgp bestpath rpki-invalid lower-priority
   ! Valid 路由：正常接受（默认行为）
   ! NotFound 路由：正常接受（默认行为）
!
! 验证命令：
!   show bgp rpki                 - 查看会话与 VRP 状态
""",
        "monitor_only": """! Arista EOS ROV 策略：monitor-only
! 策略说明：仅启用 RPKI 验证，不干预路由选择
! 风险提示：所有路由均放行，仅用于监控与统计
router bgp {{ asn }}
   ! 启用 RPKI 验证（仅监控，不 reject/lower-priority）
   ! 不配置 rpki-invalid 策略，仅记录验证状态
   ! Valid 路由：正常接受
   ! Invalid 路由：正常接受（仅监控）
   ! NotFound 路由：正常接受
!
! 验证命令：
!   show bgp rpki                 - 查看会话与 VRP 状态
!   show bgp ipv4 unicast rpki    - 查看路由验证状态（仅监控）
""",
    },
    # ── Nokia SR OS ──
    "nokia_sros": {
        "drop_invalid": """# Nokia SR OS ROV 策略：drop-invalid
# 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
# 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
configure {
    policy-options {
        policy-statement "rpki-rov" {
            entry 10 {
                from {
                    validation-state invalid
                }
                action {
                    action-type reject
                }
            }
            entry 20 {
                from {
                    validation-state valid
                }
                action {
                    action-type accept
                }
            }
            entry 30 {
                from {
                    validation-state not-found
                }
                action {
                    action-type accept
                }
            }
        }
    }
    router "Base" {
        bgp {
            import "rpki-rov"
        }
    }
}
# 验证命令：
#   show router bgp rpki          - 查看会话状态
#   show router bgp routes rpki   - 查看路由验证状态
""",
        "de_preference_invalid": """# Nokia SR OS ROV 策略：de-preference-invalid
# 策略说明：降低 Invalid 路由优先级，所有路由均放行
# 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
configure {
    policy-options {
        policy-statement "rpki-rov-depreference" {
            entry 10 {
                from {
                    validation-state invalid
                }
                action {
                    action-type accept
                    local-preference {{ localpref_invalid }}
                }
            }
            entry 20 {
                from {
                    validation-state valid
                }
                action {
                    action-type accept
                    local-preference {{ localpref_valid }}
                }
            }
            entry 30 {
                from {
                    validation-state not-found
                }
                action {
                    action-type accept
                    local-preference {{ localpref_not_found }}
                }
            }
        }
    }
    router "Base" {
        bgp {
            import "rpki-rov-depreference"
        }
    }
}
# 验证命令：
#   show router bgp rpki          - 查看会话状态
""",
        "monitor_only": """# Nokia SR OS ROV 策略：monitor-only
# 策略说明：仅启用 RPKI 验证，不干预路由选择
# 风险提示：所有路由均放行，仅用于监控与统计
configure {
    router "Base" {
        bgp {
            rpki {
                server "{{ rtr_server }}" {
                    port {{ rtr_port }}
                    refresh-time {{ refresh_interval | default 3600 }}
                    purge-time {{ expire_interval | default 7200 }}
                }
            }
            # 不配置 import 策略，所有路由均接受
            # Valid 路由：正常接受
            # Invalid 路由：正常接受（仅监控）
            # NotFound 路由：正常接受
        }
    }
}
# 验证命令：
#   show router bgp rpki          - 查看会话状态
#   show router bgp routes rpki   - 查看路由验证状态（仅监控）
""",
    },
    # ── FRRouting ──
    "frr": {
        "drop_invalid": """! FRRouting ROV 策略：drop-invalid
! 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
! 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
router bgp {{ asn }}
 bgp rpki bestpath use-policies
 ! 拒绝 Invalid 路由（drop-invalid）
 bgp rpki bestpath invalid reject
 ! Valid 路由：正常接受（默认行为）
 ! NotFound 路由：正常接受（默认行为）
!
! 验证命令：
!   show bgp rpki servers         - 查看 RTR 会话
!   show bgp rpki table           - 查看 VRP 缓存
!   show bgp ipv4 unicast rpki    - 查看路由验证状态
""",
        "de_preference_invalid": """! FRRouting ROV 策略：de-preference-invalid
! 策略说明：降低 Invalid 路由优先级，所有路由均放行
! 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
router bgp {{ asn }}
 bgp rpki bestpath use-policies
 ! 降低 Invalid 路由优先级（de-preference-invalid）
 bgp rpki bestpath invalid de-preference
 ! Valid 路由：正常接受（默认行为）
 ! NotFound 路由：正常接受（默认行为）
!
! 验证命令：
!   show bgp rpki servers         - 查看 RTR 会话
!   show bgp rpki table           - 查看 VRP 缓存
""",
        "monitor_only": """! FRRouting ROV 策略：monitor-only
! 策略说明：仅启用 RPKI 验证，不干预路由选择
! 风险提示：所有路由均放行，仅用于监控与统计
router bgp {{ asn }}
 ! 启用 RPKI 验证（仅监控，不 reject/de-preference）
 bgp rpki bestpath use-policies
 ! Valid 路由：正常接受
 ! Invalid 路由：正常接受（仅监控）
 ! NotFound 路由：正常接受
!
! 验证命令：
!   show bgp rpki servers         - 查看 RTR 会话
!   show bgp rpki table           - 查看 VRP 缓存
!   show bgp ipv4 unicast rpki    - 查看路由验证状态（仅监控）
""",
    },
    # ── BIRD ──
    "bird": {
        "drop_invalid": """# BIRD ROV 策略：drop-invalid
# 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
# 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
filter rpki_filter_drop {
    # Invalid 路由：拒绝
    if roa_check(rpki_cache_1, net, bgp_path.last) = ROUTE_INVALID then
        reject;
    # Valid 路由：接受
    if roa_check(rpki_cache_1, net, bgp_path.last) = ROUTE_VALID then
        accept;
    # NotFound 路由：接受
    accept;
}
# 应用到 BGP 邻居
protocol bgp bgp_uplink_1 {
    local {{ asn }} as {{ asn }};
    neighbor 10.0.0.2 as 64513;
    import filter rpki_filter_drop;
    export all;
}
# 验证命令：
#   birdc show protocols           - 查看 RTR 会话状态
#   birdc show route protocol rpki_cache_1 - 查看 VRP
""",
        "de_preference_invalid": """# BIRD ROV 策略：de-preference-invalid
# 策略说明：降低 Invalid 路由优先级，所有路由均放行
# 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
filter rpki_filter_depreference {
    # Invalid 路由：降低 localpref 后接受
    if roa_check(rpki_cache_1, net, bgp_path.last) = ROUTE_INVALID then {
        bgp_local_pref = {{ localpref_invalid }};
        accept;
    }
    # Valid 路由：提高 localpref 后接受
    if roa_check(rpki_cache_1, net, bgp_path.last) = ROUTE_VALID then {
        bgp_local_pref = {{ localpref_valid }};
        accept;
    }
    # NotFound 路由：默认 localpref 后接受
    bgp_local_pref = {{ localpref_not_found }};
    accept;
}
# 应用到 BGP 邻居
protocol bgp bgp_uplink_1 {
    local {{ asn }} as {{ asn }};
    neighbor 10.0.0.2 as 64513;
    import filter rpki_filter_depreference;
    export all;
}
# 验证命令：
#   birdc show protocols           - 查看 RTR 会话状态
""",
        "monitor_only": """# BIRD ROV 策略：monitor-only
# 策略说明：仅启用 RPKI 验证，不干预路由选择
# 风险提示：所有路由均放行，仅用于监控与统计
# 不应用 ROV 过滤，所有路由均接受
protocol bgp bgp_uplink_1 {
    local {{ asn }} as {{ asn }};
    neighbor 10.0.0.2 as 64513;
    import all;  # 所有路由均接受（仅监控）
    export all;
}
# Valid 路由：正常接受
# Invalid 路由：正常接受（仅监控）
# NotFound 路由：正常接受
# 验证命令：
#   birdc show protocols           - 查看 RTR 会话状态
#   birdc show route protocol rpki_cache_1 - 查看 VRP
""",
    },
    # ── OpenBGPD ──
    "openbgpd": {
        "drop_invalid": """# OpenBGPD ROV 策略：drop-invalid
# 策略说明：拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行
# 风险提示：Invalid 路由将被完全丢弃，请确认 ROA 数据准确
# 拒绝 RPKI Invalid 路由
deny from any rpki invalid
# 接受 Valid 路由
allow from any rpki valid
# 接受 NotFound 路由
allow from any rpki not-found
# 验证命令：
#   bgpctl show rtr               - 查看 RTR 会话
#   bgpctl show rib validated     - 查看 VRP
""",
        "de_preference_invalid": """# OpenBGPD ROV 策略：de-preference-invalid
# 策略说明：降低 Invalid 路由优先级，所有路由均放行
# 风险提示：Invalid 路由仍可达，但优先级降低，适合过渡期使用
# 对 Invalid 路由降低 localpref
match from any rpki invalid set { localpref {{ localpref_invalid }} }
# 对 Valid 路由提高 localpref
match from any rpki valid set { localpref {{ localpref_valid }} }
# 对 NotFound 路由设置默认 localpref
match from any rpki not-found set { localpref {{ localpref_not_found }} }
# 所有路由均接受
allow from any
# 验证命令：
#   bgpctl show rtr               - 查看 RTR 会话
""",
        "monitor_only": """# OpenBGPD ROV 策略：monitor-only
# 策略说明：仅启用 RPKI 验证，不干预路由选择
# 风险提示：所有路由均放行，仅用于监控与统计
# 不配置 rpki 过滤规则，所有路由均接受
# Valid 路由：正常接受
# Invalid 路由：正常接受（仅监控）
# NotFound 路由：正常接受
allow from any
allow to any
# 验证命令：
#   bgpctl show rtr               - 查看 RTR 会话
#   bgpctl show rib validated     - 查看 VRP
""",
    },
}


def get_default_template(
    vendor: str, template_type: str
) -> str | None:
    """获取指定厂商与类型的默认模板内容。

    Args:
        vendor: 厂商代码
        template_type: 模板类型

    Returns:
        模板内容字符串，不存在时返回 None
    """
    return DEFAULT_TEMPLATES.get(vendor, {}).get(template_type)


def get_policy_template(vendor: str, policy: str) -> str | None:
    """获取指定厂商与策略的 ROV 模板内容。

    Args:
        vendor: 厂商代码
        policy: ROV 策略（drop_invalid/de_preference_invalid/monitor_only）

    Returns:
        模板内容字符串，不存在时返回 None
    """
    return POLICY_TEMPLATES.get(vendor, {}).get(policy)


def list_policies() -> list[dict[str, Any]]:
    """列出所有支持的 ROV 策略。

    Returns:
        策略信息字典列表，包含 policy、name、description
    """
    descriptions: dict[str, str] = {
        "drop_invalid": "拒绝 RPKI Invalid 路由，Valid 与 NotFound 路由放行",
        "de_preference_invalid": "降低 Invalid 路由优先级，所有路由均放行",
        "monitor_only": "仅启用 RPKI 验证，不干预路由选择",
    }
    return [
        {
            "policy": policy,
            "name": name,
            "description": descriptions.get(policy, ""),
        }
        for policy, name in POLICY_NAMES.items()
    ]


def list_policy_templates_for_vendor(vendor: str) -> list[dict[str, Any]]:
    """列出指定厂商的所有策略模板。

    Args:
        vendor: 厂商代码

    Returns:
        策略模板信息字典列表，包含 policy、name、content
    """
    templates = POLICY_TEMPLATES.get(vendor, {})
    result: list[dict[str, Any]] = []
    for policy, content in templates.items():
        result.append(
            {
                "policy": policy,
                "name": POLICY_NAMES.get(policy, policy),
                "content": content,
            }
        )
    return result


def list_vendors() -> list[dict[str, Any]]:
    """列出所有支持的厂商。

    Returns:
        厂商信息字典列表，包含 vendor、name、template_types
    """
    result: list[dict[str, Any]] = []
    for vendor, name in VENDOR_NAMES.items():
        templates = DEFAULT_TEMPLATES.get(vendor, {})
        result.append(
            {
                "vendor": vendor,
                "name": name,
                "template_types": list(templates.keys()),
            }
        )
    return result


def list_default_templates(vendor: str) -> list[dict[str, Any]]:
    """列出指定厂商的所有默认模板。

    Args:
        vendor: 厂商代码

    Returns:
        模板信息字典列表，包含 name、vendor、template_type、content、
        variables、description、enabled
    """
    templates = DEFAULT_TEMPLATES.get(vendor, {})
    name = VENDOR_NAMES.get(vendor, vendor)
    result: list[dict[str, Any]] = []
    for template_type, content in templates.items():
        type_names = {
            "rtr_client": "RTR 客户端配置",
            "rov_policy": "ROV 策略配置",
            "rollback": "回滚配置",
            "risk_notice": "风险提示",
        }
        result.append(
            {
                "name": f"{name} - {type_names.get(template_type, template_type)}",
                "vendor": vendor,
                "template_type": template_type,
                "content": content,
                "variables": COMMON_VARIABLES,
                "description": f"{name} 默认{type_names.get(template_type, template_type)}模板",
                "enabled": True,
            }
        )
    return result


__all__ = [
    "COMMON_VARIABLES",
    "DEFAULT_TEMPLATES",
    "POLICY_NAMES",
    "POLICY_TEMPLATES",
    "VENDOR_NAMES",
    "get_default_template",
    "get_policy_template",
    "list_default_templates",
    "list_policies",
    "list_policy_templates_for_vendor",
    "list_vendors",
]
