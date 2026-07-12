# TFLite Micro 库链接配置

## 库文件位置
- 库文件：`libraries/lib/libtensorflow-microlite.a`
- 头文件：`libraries/ml-tflite-micro/tensorflow/`
- 模型文件：`libraries/tflite-micro/models/hey_jarvis_model.h`

## RT-Thread Studio 配置步骤

### 1. 添加库路径
右键项目 → Properties → C/C++ Build → Settings → Tool Settings

**GCC C++ Linker → Libraries**
- Library search path (-L): 添加 `"${workspace_loc:/${ProjName}/libraries/lib}"`
- Libraries (-l): 添加 `tensorflow-microlite`

### 2. 添加头文件路径
**GCC C++ Compiler → Includes**
- Include paths (-I): 添加以下路径
  - `"${workspace_loc:/${ProjName}/libraries/ml-tflite-micro}"`
  - `"${workspace_loc:/${ProjName}/libraries/tflite-micro/models}"`

### 3. 添加编译宏定义
**GCC C++ Compiler → Preprocessor**
- Defined symbols (-D): 添加
  - `TF_LITE_STATIC_MEMORY`
  - `TF_LITE_STRIP_ERROR_STRINGS`

### 4. 启用 C++11
**GCC C++ Compiler → Miscellaneous**
- Other flags: 确保包含 `-std=c++11` 或 `-std=gnu++11`

## 手动修改 Makefile（临时方案）

如果 RT-Thread Studio 配置不生效，可以手动修改：

编辑 `Debug/makefile` 第76行，在链接命令末尾添加：
```makefile
-L"../libraries/lib" -ltensorflow-microlite -lstdc++
```

完整命令示例：
```makefile
rtthread.elf: $(OBJS) $(USER_OBJS)
	arm-none-eabi-gcc -T "..." ... -o "rtthread.elf" $(OBJS) $(USER_OBJS) $(LIBS) \
	-L"../libraries/lib" -ltensorflow-microlite -lstdc++
```

## 编译顺序

1. 先编译 C 文件
2. 再编译 C++ 文件 (wake_word_tflite.cpp)
3. 最后链接所有目标文件和库

## 注意事项

- TFLite Micro 是 C++ 库，需要链接 libstdc++
- 确保使用 arm-none-eabi-g++ 编译 .cpp 文件
- 模型数据较大 (52KB)，确保 Flash 空间足够
