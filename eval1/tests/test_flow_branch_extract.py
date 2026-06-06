from eval1.layer1.flow_branch_extract import is_flow_branch_line, parse_branch_line


def test_is_flow_branch_line_with_and_without_bullet():
    assert is_flow_branch_line("- 若是负责人 → 进入第2步")
    assert is_flow_branch_line("若是负责人 → 进入第2步")
    assert is_flow_branch_line("若低延迟直播已显示 → 直接使用")
    assert not is_flow_branch_line("**参考话术：** 我们对直播产品做了升级")


def test_parse_branch_line():
    parsed = parse_branch_line("若不知情 → 说明前端当时未开放")
    assert parsed == ("不知情", "说明前端当时未开放")
