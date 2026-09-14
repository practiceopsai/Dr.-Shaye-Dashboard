import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextProps, View, ViewProps } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
export const colors = { ink: '#17251f', muted: '#617268', green: '#234d3c', pale: '#eaf0e9', gold: '#956922', cream: '#f4f1e9', paper: '#fbfaf6', line: '#dedfd8', red: '#a53d32', white: '#ffffff' };
export type IconName = React.ComponentProps<typeof Ionicons>['name'];
export const Icon = ({ name, color = colors.green, size = 21 }: { name: IconName; color?: string; size?: number }) => <Ionicons name={name} size={size} color={color} accessible={false} />;
export function Body({ style, ...props }: TextProps) { return <Text {...props} style={[s.body, style]} />; }
export function Small({ style, ...props }: TextProps) { return <Text {...props} style={[s.small, style]} />; }
export function Title({ children }: { children: React.ReactNode }) { return <Text accessibilityRole="header" style={s.title}>{children}</Text>; }
export function Heading({ children }: { children: React.ReactNode }) { return <Text accessibilityRole="header" style={s.heading}>{children}</Text>; }
export function Panel({ style, ...props }: ViewProps) { return <View {...props} style={[s.panel, style]} />; }
export function Kicker({ children }: { children: React.ReactNode }) { return <Text style={s.kicker}>{children}</Text>; }
export function Button({ label, onPress, icon, secondary, disabled, busy, destructive }: {
  label: string; onPress: () => void; icon?: IconName; secondary?: boolean; disabled?: boolean; busy?: boolean; destructive?: boolean;
}) {
  const color = secondary ? (destructive ? colors.red : colors.green) : colors.white;
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: Boolean(disabled || busy), busy }}
    onPress={onPress} disabled={disabled || busy} style={({ pressed }) => [s.button, secondary && s.secondary, (disabled || busy) && { opacity: .45 }, pressed && { opacity: .7 }]}>
    {busy ? <ActivityIndicator color={color} /> : icon ? <Icon name={icon} color={color} size={19} /> : null}
    <Text style={[s.buttonText, { color }]}>{label}</Text>
  </Pressable>;
}
export function Notice({ children, danger = false }: { children: React.ReactNode; danger?: boolean }) {
  return <View accessibilityRole="alert" style={[s.notice, danger && { backgroundColor: '#fbece8' }]}><Icon name={danger ? 'alert-circle-outline' : 'information-circle-outline'} color={danger ? colors.red : colors.green} /><Body style={{ flex: 1, color: danger ? colors.red : colors.green }}>{children}</Body></View>;
}
export function Empty({ title, message, icon = 'leaf-outline' }: { title: string; message: string; icon?: IconName }) {
  return <Panel style={{ paddingVertical: 32, alignItems: 'center' }}><Icon name={icon} size={32} /><Heading>{title}</Heading><Body style={{ textAlign: 'center', color: colors.muted }}>{message}</Body></Panel>;
}
export const s = StyleSheet.create({
  body: { fontSize: 15, lineHeight: 23, color: colors.ink },
  small: { fontSize: 12, lineHeight: 18, color: colors.muted },
  title: { fontSize: 32, lineHeight: 39, fontWeight: '700', color: colors.ink, letterSpacing: -.8 },
  heading: { fontSize: 19, lineHeight: 26, fontWeight: '600', color: colors.ink },
  kicker: { fontSize: 11, lineHeight: 17, letterSpacing: 1.7, fontWeight: '700', color: colors.gold, textTransform: 'uppercase' },
  panel: { padding: 20, gap: 12, borderRadius: 20, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white },
  button: { minHeight: 48, paddingVertical: 12, paddingHorizontal: 18, borderRadius: 14, backgroundColor: colors.green, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  buttonText: { fontSize: 14, fontWeight: '600', flexShrink: 1, textAlign: 'center' },
  secondary: { backgroundColor: colors.pale },
  notice: { padding: 14, borderRadius: 14, backgroundColor: colors.pale, flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  between: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  gap: { gap: 16 },
  divider: { height: 1, backgroundColor: colors.line },
  input: { borderColor: colors.line, borderWidth: 1, borderRadius: 16, backgroundColor: colors.white, padding: 16, minHeight: 160, textAlignVertical: 'top', fontSize: 17, lineHeight: 25, color: colors.ink },
});
