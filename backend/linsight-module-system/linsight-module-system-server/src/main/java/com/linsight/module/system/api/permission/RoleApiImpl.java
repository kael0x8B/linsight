package com.linsight.module.system.api.permission;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.system.api.permission.dto.RoleRespDTO;
import com.linsight.module.system.dal.dataobject.permission.RoleDO;
import com.linsight.module.system.service.permission.RoleService;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.RestController;

import jakarta.annotation.Resource;
import java.util.Collection;
import java.util.List;

import static com.linsight.framework.common.pojo.CommonResult.success;

@RestController // 提供 RESTful API 接口，给 Feign 调用
@Validated
public class RoleApiImpl implements RoleApi {

    @Resource
    private RoleService roleService;

    @Override
    public CommonResult<Boolean> validRoleList(Collection<Long> ids) {
        roleService.validateRoleList(ids);
        return success(true);
    }

    @Override
    public CommonResult<RoleRespDTO> getRole(Long id) {
        RoleDO role = roleService.getRole(id);
        return success(BeanUtils.toBean(role, RoleRespDTO.class));
    }

    @Override
    public CommonResult<List<RoleRespDTO>> getRoleList(Collection<Long> ids) {
        List<RoleDO> list = roleService.getRoleList(ids);
        return success(BeanUtils.toBean(list, RoleRespDTO.class));
    }

}
