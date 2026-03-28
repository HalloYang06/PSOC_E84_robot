#!/bin/bash
# OpenClaw Skills 管理工具

SKILLS_DIR="/home/pi/.openclaw/agents/main/skills"

show_help() {
    echo "========================================="
    echo "OpenClaw Skills 管理工具"
    echo "========================================="
    echo ""
    echo "用法: $0 <命令> [参数]"
    echo ""
    echo "命令:"
    echo "  list              - 列出所有可用的 skills"
    echo "  test <skill>      - 测试指定的 skill"
    echo "  run <skill> [args] - 运行指定的 skill"
    echo "  help              - 显示帮助"
    echo ""
    echo "示例:"
    echo "  $0 list"
    echo "  $0 test system_status"
    echo "  $0 run find_camera"
    echo "  $0 run take_photo /dev/video45 /home/pi/test.jpg"
    echo ""
}

list_skills() {
    echo "========================================="
    echo "可用的 OpenClaw Skills"
    echo "========================================="
    echo ""

    cd "$SKILLS_DIR"
    for skill in *.sh; do
        if [ -f "$skill" ]; then
            # 提取描述
            desc=$(grep "^# 描述:" "$skill" | sed 's/# 描述: //')
            printf "%-30s %s\n" "$skill" "$desc"
        fi
    done

    echo ""
    echo "总计: $(ls -1 *.sh 2>/dev/null | wc -l) 个 skills"
}

test_skill() {
    local skill="$1"

    if [ -z "$skill" ]; then
        echo "错误: 请指定要测试的 skill"
        echo "用法: $0 test <skill>"
        exit 1
    fi

    if [ ! -f "$SKILLS_DIR/$skill" ]; then
        echo "错误: Skill '$skill' 不存在"
        echo "运行 '$0 list' 查看可用的 skills"
        exit 1
    fi

    echo "========================================="
    echo "测试 Skill: $skill"
    echo "========================================="
    echo ""

    "$SKILLS_DIR/$skill"
}

run_skill() {
    local skill="$1"
    shift

    if [ -z "$skill" ]; then
        echo "错误: 请指定要运行的 skill"
        echo "用法: $0 run <skill> [参数]"
        exit 1
    fi

    if [ ! -f "$SKILLS_DIR/$skill" ]; then
        echo "错误: Skill '$skill' 不存在"
        echo "运行 '$0 list' 查看可用的 skills"
        exit 1
    fi

    "$SKILLS_DIR/$skill" "$@"
}

# 主程序
case "${1:-help}" in
    list)
        list_skills
        ;;
    test)
        test_skill "$2"
        ;;
    run)
        shift
        run_skill "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "错误: 未知命令 '$1'"
        echo ""
        show_help
        exit 1
        ;;
esac
