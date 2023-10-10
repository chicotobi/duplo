


if 'patches' not in st.session_state:
  st.session_state.patches = []
  st.session_state.pos0 = [pos0]

with st.container():
  col1, col2, col3, col4 = st.columns(4)
  with col1:
    if st.button(':arrow_up:'):
      pos0 = st.session_state.pos0[-1]
      patch, pos0 = add_straight(pos0)
      st.session_state.pos0.append(pos0)
      st.session_state.patches.append(patch)
    
  with col2:
    if st.button(':arrow_left:'):
      pos0 = st.session_state.pos0[-1]
      patch, pos0 = add_curve_left(pos0)
      st.session_state.pos0.append(pos0)
      st.session_state.patches.append(patch)
      
  with col3:
    if st.button(':arrow_right:'):
      pos0 = st.session_state.pos0[-1]
      patch, pos0 = add_curve_right(pos0)
      st.session_state.pos0.append(pos0)
      st.session_state.patches.append(patch)
  
  with col4:
    if st.button(':x:'):
      st.session_state.pos0.pop()
      st.session_state.patches.pop()
    
plt.cla()
fig, ax = plt.subplots()
for p in st.session_state.patches:
  p2 = copy(p)
  ax.add_patch(p2)

pos0 = st.session_state.pos0[-1]
p1, p2 = pos0
x1, y1 = p1
x2, y2 = p2
x3 = (x1+x2)/2 + (y1-y2)
y3 = (y1+y2)/2 - (x1-x2)
ax.plot([x1,x2,x3,x1],[y1,y2,y3,y1],'-g',linewidth=1)

ax.set_xlim((-30,30))
ax.set_ylim((-30,30))
plt.gca().set_aspect('equal')
plt.tick_params(left = False, right = False , labelleft = False , labelbottom = False, bottom = False) 
st.pyplot(fig)