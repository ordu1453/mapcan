<script setup lang="ts">
// mapcan logo: the icon and the text in its font (Sora ExtraBold) and colors: "map" like the white "m"
// on blue, "can" like the amber "c".
defineProps<{ size?: number }>();
</script>

<template>
  <span class="brandmark" :style="size ? { fontSize: `${size}px` } : undefined">
    <img class="brandmark-icon" src="/favicon.svg" alt="" aria-hidden="true" />
    <span class="brandmark-word"><span class="brandmark-map">map</span><span class="brandmark-can">can</span></span>
  </span>
</template>
