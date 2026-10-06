<script setup lang="ts">
// Логотип mapcan: иконка и надпись в её шрифте (Sora ExtraBold) и цветах — «map» как белая «m»
// на синем, «can» как янтарная «c».
defineProps<{ size?: number }>();
</script>

<template>
  <span class="brandmark" :style="size ? { fontSize: `${size}px` } : undefined">
    <img class="brandmark-icon" src="/favicon.svg" alt="" aria-hidden="true" />
    <span class="brandmark-word"><span class="brandmark-map">map</span><span class="brandmark-can">can</span></span>
  </span>
</template>
