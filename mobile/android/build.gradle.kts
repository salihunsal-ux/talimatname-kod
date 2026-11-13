allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

// Sürüm derlemesindeki "lintVital" görevleri kapalı: kamera eklentisinde
// lint'in kendi hatasıyla çöküyor ("Unexpected failure during lint
// analysis ... a bug in lint") ve APK çıkmıyor. Lint bizim kodumuzu
// denetlemiyor zaten; Dart tarafı `flutter analyze` ile denetleniyor.
subprojects {
    tasks.matching { it.name.startsWith("lintVital") }.configureEach {
        enabled = false
    }
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
